import asyncio
import copy
import logging
import pathlib
import random
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from intervaltree import IntervalTree
from pydantic import BaseModel

import woke.compile
import woke.config
from woke.ast.ir.declaration.contract_definition import ContractDefinition
from woke.ast.ir.declaration.function_definition import FunctionDefinition
from woke.ast.ir.declaration.modifier_definition import ModifierDefinition
from woke.ast.ir.expression.function_call import FunctionCall
from woke.ast.ir.meta.source_unit import SourceUnit
from woke.ast.ir.reference_resolver import CallbackParams, ReferenceResolver
from woke.ast.ir.statement.abc import StatementAbc
from woke.ast.ir.statement.block import Block
from woke.ast.ir.statement.do_while_statement import DoWhileStatement
from woke.ast.ir.statement.expression_statement import ExpressionStatement
from woke.ast.ir.statement.for_statement import ForStatement
from woke.ast.ir.statement.if_statement import IfStatement
from woke.ast.ir.statement.while_statement import WhileStatement
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import AstSolc
from woke.compile import SolcOutput
from woke.compile.compilation_unit import CompilationUnit
from woke.compile.solc_frontend import SolcOutputSelectionEnum
from woke.json_rpc import communicator
from woke.json_rpc.data_model import JsonRpcTransaction, JsonRpcTransactionTrace

logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)


def _to_camel(s: str) -> str:
    split = s.split("_")
    return split[0].lower() + "".join([w.capitalize() for w in split[1:]])


class Exportable(BaseModel):
    class Config:
        alias_generator = _to_camel
        allow_mutation = False
        allow_population_by_field_name = True


@dataclass
class BytecodeInfo:
    opcodes: str
    source_map: str


def _get_line_col_from_offset(
    location: int, line_intervals: IntervalTree
) -> Tuple[int, int]:
    if len(line_intervals[location]) != 1:
        logger.debug(f"Getting location for {location} in {line_intervals}")
        raise IndexError(f"No or too many line intervals for {location}")
    interval = list(line_intervals[location])[0]
    return interval.data, location - interval.begin


@dataclass
class SourceMapPcRecord:
    fn_name: str
    offset: Tuple[int, int]
    jump_type: str
    op: str
    argument: Optional[int]
    size: int


class LocationInfo:
    byte_offsets: Tuple[int, int]
    ide_pos: Tuple[Tuple[int, int], Tuple[int, int]]

    def __init__(self, byte_location: Tuple[int, int], line_intervals: IntervalTree):
        self.byte_offsets = byte_location
        self.ide_pos = (
            _get_line_col_from_offset(byte_location[0], line_intervals),
            _get_line_col_from_offset(byte_location[1], line_intervals),
        )

    def __str__(self):
        return f"{self.byte_offsets} - {self.ide_pos}"


@dataclass
class HitCountRecord:
    hit_count: int


@dataclass
class InstrCovRecord(HitCountRecord):
    src_pc_map: SourceMapPcRecord


@dataclass
class BranchCovRecord(InstrCovRecord):
    branch: LocationInfo


@dataclass
class ModifierCovRecord(HitCountRecord):
    modifier_fn_name: str


@dataclass
class FunctionInfo:
    name: str
    name_location: LocationInfo
    body_location: Optional[LocationInfo]
    modifiers: Dict[str, LocationInfo]
    instruction_cov: Dict[int, InstrCovRecord]
    branch_cov: Dict[int, BranchCovRecord]
    modifier_cov: Dict[int, ModifierCovRecord]

    def __init__(
        self,
        fn: Union[FunctionDefinition, ModifierDefinition],
        line_intervals: IntervalTree,
    ):
        self.name = fn.canonical_name
        self.name_location = LocationInfo(fn.name_location, line_intervals)
        self.body_location = (
            LocationInfo(fn.body.byte_location, line_intervals) if fn.body else None
        )

        self.modifiers = (
            {
                mod.modifier_name.referenced_declaration.canonical_name: LocationInfo(  # type: ignore
                    mod.byte_location, line_intervals
                )
                for mod in fn.modifiers  # type: ignore
                if hasattr(mod.modifier_name.referenced_declaration, "canonical_name")
            }
            if hasattr(fn, "modifiers")
            else {}
        )

        self.instruction_cov = {}
        self.branch_cov = {}
        self.modifier_cov = {}

    def __add__(self, other):
        for pc, cov in self.instruction_cov.items():
            cov.hit_count += other.instruction_cov[pc].hit_count
        for pc, cov in self.branch_cov.items():
            cov.hit_count += other.branch_cov[pc].hit_count
        for pc, cov in self.modifier_cov.items():
            cov.hit_count += other.modifier_cov[pc].hit_count
        return self

    @property
    def calls(self):
        if len(self.branch_cov) + len(self.modifier_cov) == 0:
            return 0
        return max(
            [x.hit_count for x in self.branch_cov.values()]
            + [x.hit_count for x in self.modifier_cov.values()]
        )


class IdeCoverageRecord(Exportable):
    start_line: int
    start_column: int
    end_line: int
    end_column: int
    coverage: int
    coverage_hits: int
    message: str


class ContractCoverage:
    pc_map: Dict[int, SourceMapPcRecord]
    function_instructions: Dict[int, FunctionInfo]
    pc_instruction_cov: Dict[int, InstrCovRecord]
    pc_branch_cov: Dict[int, BranchCovRecord]
    pc_modifier_cov: Dict[int, ModifierCovRecord]

    _functions: Dict[str, FunctionInfo]
    _declaration_locations: Dict[str, Tuple[int, int]]
    _modifiers_locations: Dict[str, Dict[str, Tuple[int, int]]]
    _line_intervals: IntervalTree
    _spaces_intervals: IntervalTree

    def __init__(
        self,
        pc_map: Dict[int, SourceMapPcRecord],
        contract_def: ContractDefinition,
        line_intervals: IntervalTree,
    ):
        self.pc_map = pc_map
        self.pc_instruction_cov = {}
        self.pc_branch_cov = {}
        self.pc_modifier_cov = {}
        self.function_instructions = {}
        self.filename = str(contract_def.file.absolute())

        spaces_intervals = self._find_code_spaces_intervals(
            contract_def.source, contract_def.byte_location[0]
        )

        self._functions = {
            fn.canonical_name: FunctionInfo(fn, line_intervals)
            for fn in (contract_def.functions + contract_def.modifiers)
        }

        self._add_instruction_coverage()
        self._add_branch_coverage(contract_def, line_intervals, spaces_intervals)
        self._add_modifier_coverage()

    def __add__(self, other):
        for fn, fn_info in self._functions.items():
            fn_info += other._functions[fn]
        return self

    def add_cov(self, pc: int):
        for cov in [self.pc_branch_cov, self.pc_modifier_cov, self.pc_instruction_cov]:
            if pc in cov:
                cov[pc].hit_count += 1

    def get_ide_branch_coverage(self) -> List[Dict[str, List]]:
        """
        Returns (x,y) where x is number of executed branches and y is number of
        """

        cov_data = []
        for fn in self._functions.values():
            for rec in fn.branch_cov.values():
                (start_line, start_col), (end_line, end_col) = rec.branch.ide_pos
                coverage = int((rec.hit_count / fn.calls) * 100) if fn.calls != 0 else 0
                logger.info(
                    f"{rec.hit_count} / {fn.calls} cov {coverage} for {fn.name} and {rec.branch}"
                )
                cov_data.append(
                    IdeCoverageRecord(
                        start_line=start_line,
                        start_column=start_col,
                        end_line=end_line,
                        end_column=end_col,
                        coverage=coverage,
                        coverage_hits=rec.hit_count,
                        message=f"Execs: {rec.hit_count} / {fn.calls}",
                    ).dict(by_alias=True)
                )
        return cov_data

    def get_ide_function_calls_coverage(self) -> List[Dict[str, Any]]:
        fns_max_calls = max([fn.calls for fn in self._functions.values()])
        fns_sum_calls = sum([fn.calls for fn in self._functions.values()])

        cov_data = []
        for fn in self._functions.values():
            (start_line, start_col), (end_line, end_col) = fn.name_location.ide_pos
            coverage = ((fn.calls / fns_max_calls) * 100) if fns_max_calls != 0 else 0
            cov_data.append(
                IdeCoverageRecord(
                    start_line=start_line,
                    start_column=start_col,
                    end_line=end_line,
                    end_column=end_col,
                    coverage=coverage,
                    coverage_hits=fn.calls,
                    message=f"Execs: {fn.calls} / {fns_sum_calls}",
                ).dict(by_alias=True)
            )
        return cov_data

    def get_ide_modifier_calls_coverage(self) -> List[Dict[str, Any]]:
        cov_data = []

        for fn in self._functions.values():
            for pc, rec in fn.modifier_cov.items():
                coverage = ((rec.hit_count / fn.calls) * 100) if fn.calls != 0 else 0
                (start_line, start_col), (end_line, end_col) = fn.modifiers[
                    rec.modifier_fn_name
                ].ide_pos

                cov_data.append(
                    IdeCoverageRecord(
                        start_line=start_line,
                        start_column=start_col,
                        end_line=end_line,
                        end_column=end_col,
                        coverage=coverage,
                        coverage_hits=rec.hit_count,
                        message=f"Execs: {rec.hit_count} / {fn.calls}",
                    ).dict(by_alias=True)
                )
        return cov_data

    def _find_code_spaces_intervals(
        self, source_code: str, start_byte_offset: int
    ) -> IntervalTree:
        in_interval = False
        int_start = 0
        intervals = set()
        for i, c in enumerate(source_code):
            if c in (" ", "\t", "\n", "\r"):
                if not in_interval:
                    int_start = i
                    in_interval = True
            elif in_interval:
                intervals.add(
                    (int_start + start_byte_offset, i + start_byte_offset + 1)
                )
                in_interval = False
        return IntervalTree.from_tuples(intervals)

    def _get_source_coverage(self, instr: Dict[int, int]) -> Dict[Tuple[int, int], int]:
        source_cov = {}

        for pc, rec in self.pc_map.items():
            if pc in instr and (
                rec.offset not in source_cov or instr[pc] > source_cov[rec.offset]
            ):
                source_cov[rec.offset] = instr[pc]
        return source_cov

    def _find_modifier_call(
        self,
        starting_pc: int,
        parent_fn: FunctionInfo,
        caller_fn: FunctionInfo,
        allowed_fns: List[str],
    ):
        starting_instr = self.pc_map[starting_pc]
        act_pc = starting_pc
        logger.info(
            f"Finding modifier call at {starting_pc} in {starting_instr.fn_name}"
        )
        while True:
            if act_pc not in self.pc_map:
                logger.debug(f"PC {act_pc} is not in pc_map")
                break
            act_instr = self.pc_map[act_pc]
            if (
                act_instr.fn_name is None
                or act_instr.fn_name != starting_instr.fn_name
                or not act_instr.argument
            ):
                break

            jump_pc = act_pc + act_instr.size
            if (
                act_instr.op.startswith("PUSH")
                and jump_pc in caller_fn.instruction_cov
                and caller_fn.instruction_cov[jump_pc].src_pc_map.op.startswith("JUMP")
            ):
                jumpdest = (
                    caller_fn.instruction_cov[act_instr.argument]
                    if act_instr.argument in caller_fn.instruction_cov
                    else None
                )
                if jumpdest and jumpdest.src_pc_map.op == "JUMPDEST":
                    mod_push_pc = act_instr.argument + 1
                    mod_push = (
                        self.pc_map[mod_push_pc] if mod_push_pc in self.pc_map else None
                    )

                    if (
                        mod_push
                        and mod_push.op.startswith("PUSH")
                        and mod_push.fn_name != act_instr.fn_name
                        and mod_push.fn_name in allowed_fns
                    ):
                        mod_cov = ModifierCovRecord(
                            hit_count=0, modifier_fn_name=mod_push.fn_name
                        )
                        self.pc_modifier_cov[mod_push_pc] = mod_cov
                        parent_fn.modifier_cov[mod_push_pc] = mod_cov
                        self._find_modifier_call(
                            mod_push_pc,
                            parent_fn,
                            self._functions[mod_push.fn_name],
                            allowed_fns,
                        )
                        logger.debug(
                            f"Adding {mod_push_pc} to coverage of {parent_fn.modifier_cov}"
                        )
            act_pc = act_pc + act_instr.size

    def _add_modifier_coverage(self):
        for fn in self._functions.values():
            for pc, rec in fn.instruction_cov.items():
                jump_pc = pc + rec.src_pc_map.size
                if (
                    rec.src_pc_map.op.startswith("PUSH")
                    and jump_pc in fn.instruction_cov
                    and fn.instruction_cov[jump_pc].src_pc_map.op.startswith("JUMP")
                ):
                    self._find_modifier_call(pc, fn, fn, list(fn.modifiers.keys()))
                    logger.debug(f"{fn.name} {fn.modifiers} {fn.modifier_cov.keys()}")

    def _find_branches(
        self, statement: Union[StatementAbc, Block], branches: List[Tuple[int, int]]
    ):
        append_next = True
        stmts = [statement] if type(statement) != Block else statement.statements  # type: ignore
        for stmt in stmts:
            stmt_to = stmt.byte_location[1] - stmt.byte_location[0]
            if statement.source[stmt_to - 1] in ("{", "}"):
                stmt_to -= 1
            stmt_loc_data = (
                stmt.byte_location[0],
                stmt_to,
            )
            logger.debug(f"{stmt.byte_location} {stmt.source[:stmt_to]}")
            if append_next:
                branches.append(stmt_loc_data)
                append_next = False

            if type(stmt) == IfStatement:
                self._find_branches(stmt.true_body, branches)  # type: ignore
                if stmt.false_body:  # type: ignore
                    self._find_branches(stmt.false_body, branches)  # type: ignore
                append_next = True
            elif (
                type(stmt) in (WhileStatement, ForStatement, DoWhileStatement)
                and stmt.body  # type: ignore
            ):
                self._find_branches(stmt.body, branches)  # type: ignore
                append_next = True
            elif (
                type(stmt) == ExpressionStatement
                and type(stmt.expression) == FunctionCall  # type: ignore
            ):
                append_next = True

    def _get_function_branches(
        self,
        function_def: Union[FunctionDefinition, ModifierDefinition],
        spaces_intervals: IntervalTree,
    ) -> List[Tuple[int, int]]:
        branches: List[Tuple[int, int]] = []
        if not function_def.body:
            return []
        self._find_branches(function_def.body, branches)
        branches.sort(key=lambda b: (b[0], -b[1]))

        branches_sec = []
        last = None
        for i, branch in enumerate(branches):
            int_from = branch[0]
            if int_from == last:
                continue
            last = int_from
            branches_sec.append(branch)

        branches_fin: List[Tuple[int, int]] = []
        for i, branch in enumerate(branches_sec):
            int_from = branch[0]
            if i < len(branches) - 1:
                int_to = branches[i + 1][0]  # stretch to next branch
            else:
                int_to = function_def.body.statements[-1].byte_location[1]

            if len(spaces_intervals[int_from]) != 0:
                int_from = list(spaces_intervals[int_from])[0].end - 1

            if len(spaces_intervals[int_to]) != 0:
                int_to = list(spaces_intervals[int_to])[0].begin

            changed = True
            while changed:
                changed = False
                if (
                    function_def.source[int_to - function_def.byte_location[0] - 1]
                    in ("{", "}")
                    and len(spaces_intervals[int_to - 1]) != 0
                ):
                    int_to = list(spaces_intervals[int_to - 1])[0].begin
                    changed = True

            branches_fin.append((int_from, int_to))

        return branches_fin

    def _add_branch_coverage(
        self,
        contract_def: ContractDefinition,
        line_intervals: IntervalTree,
        spaces_intervals: IntervalTree,
    ):
        for fn_def in contract_def.functions + contract_def.modifiers:
            fn = self._functions[fn_def.canonical_name]
            if fn_def.body:
                logger.debug(f"Adding branch coverage to {fn.name}")
                branches = self._get_function_branches(fn_def, spaces_intervals)
                logger.debug(f"Found branches: {branches}")
                for branch in branches:
                    branch_loc = LocationInfo(branch, line_intervals)
                    logger.debug(f"Branch: {branch_loc}")
                    pc = self._find_branch_pc(branch)
                    if pc is None:
                        logger.debug(f"No pc found")
                        continue
                    logger.debug(
                        f"Pc: {pc} at {self.pc_map[pc].offset} {self.pc_map[pc].op}"
                    )

                    branch_cov = BranchCovRecord(
                        hit_count=0, src_pc_map=self.pc_map[pc], branch=branch_loc
                    )
                    self.pc_branch_cov[pc] = branch_cov
                    fn.branch_cov[pc] = branch_cov
                logger.debug(
                    f"Function {fn.name} has these branch detection instructions: "
                    f"{fn.branch_cov.keys()}"
                )

    def _add_instruction_coverage(self):
        for pc, rec in self.pc_map.items():
            if rec.fn_name is not None:
                cov = InstrCovRecord(hit_count=0, src_pc_map=rec)
                self._functions[rec.fn_name].instruction_cov[pc] = cov
                self.pc_instruction_cov[pc] = cov

    def _find_branch_pc(self, source_int: Tuple[int, int]) -> Optional[int]:
        interval_tree = IntervalTree.from_tuples(
            {(rec.offset[0], rec.offset[1], pc) for pc, rec in self.pc_map.items()}
        )
        intervals = [
            (i.begin, i.end - i.begin, i.data)
            for i in list(interval_tree[source_int[0] : source_int[1]])
            if i.begin >= source_int[0]
        ]

        if len(intervals) == 0:
            return None

        intervals.sort(key=lambda x: (x[0], x[1], x[2]))
        return intervals[0][2]


def _parse_opcodes(opcodes: str) -> List[Tuple[int, str, int, Optional[int]]]:
    pc_op_map = []
    opcodes_spl = opcodes.split(" ")

    pc = 0
    ignore = False

    for i, opcode in enumerate(opcodes_spl):
        if ignore:
            ignore = False
            continue

        if not opcode.startswith("PUSH"):
            pc_op_map.append((pc, opcode, 1, None))
            pc += 1
        else:
            size = int(opcode[4:]) + 1
            pc_op_map.append((pc, opcode, size, int(opcodes_spl[i + 1], 16)))
            pc += size
            ignore = True
    return pc_op_map


def _find_fn_for_source(
    interval_tree: IntervalTree, source_from: int, source_to: int
) -> Optional[str]:
    nodes = interval_tree[source_from:source_to]
    function_def_nodes = [
        n
        for n in nodes
        if type(n.data) in [FunctionDefinition, ModifierDefinition]
        and n.length() >= (source_to - source_from)
    ]
    logger.debug(f"{function_def_nodes} {nodes} {source_from}:{source_to}")
    if not function_def_nodes:
        # logger.info(f"No for {source_int}")
        return None
    max_overlap = None
    final_name = None
    for node in function_def_nodes:
        logger.debug(
            f"{source_from}:{source_to} {len(function_def_nodes)} {str(type(node.data))} {node.data.canonical_name}"
        )
        overlap = node.overlap_size(source_from, source_to) / node.length()
        logger.debug(f"overlap {overlap} {max_overlap} {source_from}:{source_to}")
        if max_overlap is None or overlap > max_overlap:
            max_overlap = overlap
            final_name = node.data.canonical_name
    return final_name


def _parse_project(
    outputs: List[Tuple[CompilationUnit, SolcOutput]]
) -> Tuple[
    Dict[pathlib.Path, SourceUnit],
    Dict[pathlib.Path, IntervalTree],
    Dict[pathlib.Path, Dict[str, BytecodeInfo]],
]:
    processed_files: Set[pathlib.Path] = set()
    reference_resolver = ReferenceResolver()
    interval_trees: Dict[pathlib.Path, IntervalTree] = {}
    source_units: Dict[pathlib.Path, SourceUnit] = {}
    bytecode_info: Dict[pathlib.Path, Dict[str, BytecodeInfo]] = {}

    for cu, output in outputs:
        for source_unit_name, info in output.sources.items():
            path = cu.source_unit_name_to_path(pathlib.PurePath(source_unit_name))

            for contract_name, contract_info in output.contracts[
                source_unit_name
            ].items():
                if contract_info.evm:
                    if path not in bytecode_info:
                        bytecode_info[path] = {}
                    if (
                        contract_info.evm.deployed_bytecode
                        and contract_info.evm.deployed_bytecode.opcodes
                        and contract_info.evm.deployed_bytecode.source_map
                    ):
                        bytecode_info[path][contract_name] = BytecodeInfo(
                            contract_info.evm.deployed_bytecode.opcodes,
                            contract_info.evm.deployed_bytecode.source_map,
                        )

            ast = AstSolc.parse_obj(info.ast)

            reference_resolver.index_nodes(ast, path, cu.hash)

            if path in processed_files:
                continue
            processed_files.add(path)
            interval_trees[path] = IntervalTree()

            init = IrInitTuple(
                path,
                path.read_bytes(),
                cu,
                interval_trees[path],
                reference_resolver,
            )
            source_units[path] = SourceUnit(init, ast)

    reference_resolver.run_post_process_callbacks(
        CallbackParams(source_units=source_units, interval_trees=interval_trees)
    )
    return source_units, interval_trees, bytecode_info


def _compile_project() -> List[Tuple[CompilationUnit, SolcOutput]]:
    config = woke.config.WokeConfig()
    config.load_configs()
    contracts_path = config.project_root_path / "contracts"
    sol_files = [path for path in contracts_path.rglob("*.sol") if path.is_file()]

    compiler = woke.compile.SolidityCompiler(config)
    outputs: List[Tuple[CompilationUnit, SolcOutput]] = asyncio.run(
        compiler.compile(
            sol_files,
            [SolcOutputSelectionEnum.ALL],
            write_artifacts=True,
            reuse_latest_artifacts=True,
            maximize_compilation_units=True,
        )
    )
    return outputs


def _parse_source_map(
    interval_tree: IntervalTree,
    source_map: str,
    pc_op_map: List[Tuple[int, str, int, Optional[int]]],
) -> Dict[int, SourceMapPcRecord]:
    pc_map = {}
    source_map_spl = source_map.split(";")

    last_data = [-1, -1, -1, None, None]
    last_fn = None
    fn_changed = False
    name_cache = {}

    for i, sm_item in enumerate(source_map_spl):
        pc, op, size, argument = pc_op_map[i]
        source_spl = sm_item.split(":")
        for x in range(len(source_spl)):
            if source_spl[x] == "":
                continue
            if x < 3:
                fn_changed = True
                last_data[x] = int(source_spl[x])
            else:
                last_data[x] = source_spl[x]

        if last_data[2] and last_data[2] != 0:
            continue

        source_interval = (last_data[0], last_data[0] + last_data[1])
        if fn_changed:
            if source_interval in name_cache:
                last_fn = name_cache[source_interval]
            else:
                last_fn = _find_fn_for_source(interval_tree, *source_interval)
            name_cache[source_interval] = last_fn

        if last_fn:
            pc_map[pc] = SourceMapPcRecord(
                last_fn, source_interval, last_data[3], op, argument, size
            )
        logger.debug(f"{pc} {i} {source_interval}, {last_fn}, {fn_changed}")

    return pc_map


def _get_line_intervals(source: str) -> IntervalTree:
    location = 0
    intervals = set()
    # splitlines deletes blank lines sometimes?
    for line_num, line in enumerate(source.splitlines(keepends=True)):
        intervals.add((location, location + len(line), line_num))
        location += len(line)
    return IntervalTree.from_tuples(intervals)


def _construct_coverage_data() -> Dict[str, ContractCoverage]:
    time.sleep(random.randint(2, 4))
    outputs = _compile_project()
    source_units, interval_trees, bytecode_infos = _parse_project(outputs)
    contracts_cov = {}
    for unit_path, unit in source_units.items():
        line_intervals = _get_line_intervals(unit.file.read_text())
        for contract in unit.contracts:
            if (
                unit_path not in bytecode_infos
                or contract.canonical_name not in bytecode_infos[unit_path]
            ):
                continue
            opcodes = bytecode_infos[unit_path][contract.canonical_name].opcodes
            source_map = bytecode_infos[unit_path][contract.canonical_name].source_map

            pc_op_map = _parse_opcodes(opcodes)
            pc_map = _parse_source_map(interval_trees[unit_path], source_map, pc_op_map)

            contracts_cov[contract.canonical_name] = ContractCoverage(
                pc_map, contract, line_intervals
            )
    return contracts_cov


class Coverage:
    contracts_cov: Dict[str, ContractCoverage]
    contracts_per_trans_cov: Dict[str, ContractCoverage]

    def __init__(self):
        cov = _construct_coverage_data()
        self.contracts_cov = cov
        self.contracts_per_trans_cov = copy.deepcopy(cov)

    def __add__(self, other):
        for fp, cov in self.contracts_cov.items():
            cov += other.contracts_cov[fp]
        for fp, cov in self.contracts_per_trans_cov.items():
            cov += other.contracts_per_trans_cov[fp]
        return self

    def get_covered_contracts(self):
        """
        Returns covered contract names that can be then used in other methods
        """
        return self.contracts_cov.keys()

    def get_contract_coverage(
        self, contract_name: str, per_transaction: bool
    ) -> ContractCoverage:
        """
        Returns ContractCoverage for given contract name
        """
        if per_transaction:
            return self.contracts_per_trans_cov[contract_name]
        return self.contracts_cov[contract_name]

    def get_contract_ide_coverage(
        self, per_transaction: bool
    ) -> Dict[str, List[Dict[str, List]]]:
        """
        Returns dictionary where key is an absolute filepath and value is ContractCoverage
        """

        cov_per_file = {}
        for cov in (
            self.contracts_per_trans_cov.values()
            if per_transaction
            else self.contracts_cov.values()
        ):
            if cov.filename not in cov_per_file:
                cov_per_file[cov.filename] = []

            cov_per_file[cov.filename] += cov.get_ide_branch_coverage()
            cov_per_file[cov.filename] += cov.get_ide_function_calls_coverage()
            cov_per_file[cov.filename] += cov.get_ide_modifier_calls_coverage()
        return cov_per_file

    async def process_trace(self, contract_name: str, trace: JsonRpcTransactionTrace):
        """
        Processes JsonRpcTransactionTrace and it's struct_logs
        """
        transaction_pcs = set()
        contract_cov = self.contracts_cov[contract_name]
        for struct_log in trace.struct_logs:
            pc = int(struct_log.pc)
            if pc in contract_cov.pc_map:
                logger.debug(
                    f"{pc} {struct_log.op} {contract_cov.pc_map[pc].op} "
                    f"{contract_cov.pc_map[pc].argument if contract_cov.pc_map[pc].argument else None} "
                    f"from {contract_cov.pc_map[pc].fn_name} {contract_cov.pc_map[pc].offset} is "
                    f"executed "
                )
            else:
                logger.debug(f"{pc} {struct_log.op} is executed")
            if pc not in transaction_pcs:
                self.contracts_per_trans_cov[contract_name].add_cov(pc)
                transaction_pcs.add(pc)
            self.contracts_cov[contract_name].add_cov(pc)


class CoverageProvider:
    _comm: communicator.JsonRpcCommunicator
    _coverage: Coverage
    _last_covered_block: int

    def __init__(
        self,
        comm: communicator.JsonRpcCommunicator,
        coverage: Coverage,
        starter_block: Optional[int] = None,
    ):
        self._comm = comm
        self._coverage = coverage
        self._last_covered_block = starter_block if starter_block is not None else 0

    def get_coverage(self) -> Coverage:
        return self._coverage

    async def update_coverage(self, contracts: Dict[str, str]):
        """
        Checks for latest transactions on blockchain for
        """
        last_block = await self._comm.eth_block_number()
        if (
            self._last_covered_block > last_block
        ):  # chain was reset -> reset last_covered_block
            self._last_covered_block = 0

        for block_number in range(self._last_covered_block, last_block):
            block_info = await self._comm.eth_get_block_by_number(
                block_number, full_transactions=True
            )
            for transaction in block_info.transactions:
                if type(transaction) is not JsonRpcTransaction:
                    raise TypeError("Transactions are not JsonRpcTransaction")
                if (
                    not transaction.to_addr
                    or transaction.to_addr not in contracts.keys()
                ):
                    continue
                trace = await self._comm.debug_trace_transaction(
                    transaction.hash,
                    disable_storage=True,
                    disable_memory=True,
                    disable_stack=True,
                )
                contract_name = contracts[transaction.to_addr]
                await self._coverage.process_trace(contract_name, trace)
        self._last_covered_block = last_block


def get_merged_ide_coverage(
    coverages: List[Coverage],
) -> Optional[
    Tuple[Dict[str, List[Dict[str, List]]], Dict[str, List[Dict[str, List]]]]
]:
    if len(coverages) < 0:
        return None
    cov = copy.deepcopy(coverages[0])
    for c in coverages[1:]:
        cov += c
    return cov.get_contract_ide_coverage(False), cov.get_contract_ide_coverage(True)
