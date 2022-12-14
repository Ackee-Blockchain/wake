import asyncio
import copy
import logging
import pathlib
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from intervaltree import IntervalTree
from pydantic import BaseModel

import woke.compile
import woke.config
from woke.ast.enums import GlobalSymbolsEnum
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
from woke.compile.solc_frontend import (
    SolcOutputErrorSeverityEnum,
    SolcOutputSelectionEnum,
)
from woke.config import WokeConfig
from woke.testing import default_chain
from woke.testing.core import (
    Address,
    get_fqn_from_address,
    get_fqn_from_deployment_code,
)
from woke.testing.development_chains import DevChainABC
from woke.utils.file_utils import is_relative_to

logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)


def _to_camel(s: str) -> str:
    split = s.split("_")
    return split[0].lower() + "".join([w.capitalize() for w in split[1:]])


class Exportable(BaseModel):
    class Config:
        alias_generator = _to_camel
        allow_mutation = True
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
    source_id: int
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

        self.modifiers = {}
        if isinstance(fn, FunctionDefinition):
            for mod in fn.modifiers:
                if not isinstance(
                    mod.modifier_name.referenced_declaration, GlobalSymbolsEnum
                ):
                    self.modifiers[
                        mod.modifier_name.referenced_declaration.canonical_name
                    ] = LocationInfo(mod.byte_location, line_intervals)

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
    coverage_hits: int
    calls: int

    def __add__(self, other):
        self.coverage_hits += other.coverage_hits
        self.calls += other.calls
        return self


def _find_code_spaces_intervals(
    source_code: str, start_byte_offset: int
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
            intervals.add((int_start + start_byte_offset, i + start_byte_offset + 1))
            in_interval = False
    return IntervalTree.from_tuples(intervals)


class ContractCoverage:
    pc_map: Dict[int, SourceMapPcRecord]
    pc_function: Dict[int, FunctionInfo]
    pc_instruction_cov: Dict[int, InstrCovRecord]
    pc_branch_cov: Dict[int, BranchCovRecord]
    pc_modifier_cov: Dict[int, ModifierCovRecord]
    functions: Dict[str, FunctionInfo]

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
        self.pc_function = {}
        self.filename = str(contract_def.file.absolute())
        self.functions = {}

        for base_contract_def in contract_def.linearized_base_contracts:
            spaces_intervals = _find_code_spaces_intervals(
                base_contract_def.source, base_contract_def.byte_location[0]
            )

            self.functions.update(
                {
                    fn.canonical_name: FunctionInfo(fn, line_intervals)
                    for fn in (
                        base_contract_def.functions + base_contract_def.modifiers
                    )
                }
            )

            self._add_branch_coverage(
                base_contract_def, line_intervals, spaces_intervals
            )

        for pc, rec in self.pc_map.items():
            if rec.fn_name in self.functions:
                self.pc_function[pc] = self.functions[rec.fn_name]

        self._add_instruction_coverage()
        self._add_modifier_coverage()

    def __add__(self, other):
        for fn, fn_info in self.functions.items():
            fn_info += other.functions[fn]
        for pc, rec in other.pc_instruction_cov.items():
            self.pc_instruction_cov[pc].hit_count += rec.hit_count
        for pc, rec in other.pc_branch_cov.items():
            self.pc_branch_cov[pc].hit_count += rec.hit_count
        for pc, rec in other.pc_modifier_cov.items():
            self.pc_modifier_cov[pc].hit_count += rec.hit_count
        return self

    def add_cov(self, pc: int):
        for cov in [self.pc_branch_cov, self.pc_modifier_cov, self.pc_instruction_cov]:
            if pc in cov:
                cov[pc].hit_count += 1

    def get_ide_branch_coverage(
        self,
    ) -> Dict[Tuple[Tuple[int, int], Tuple[int, int]], IdeCoverageRecord]:
        """
        Returns a list of IdeCoverageRecord for each branch
        """

        cov_data = {}
        for fn in self.functions.values():
            for rec in fn.branch_cov.values():
                (start_line, start_col), (end_line, end_col) = rec.branch.ide_pos
                logger.info(
                    f"Branch: {rec.hit_count} / {fn.calls} for {fn.name} and {rec.branch}"
                )
                cov_data[rec.branch.ide_pos] = IdeCoverageRecord(
                    start_line=start_line,
                    start_column=start_col,
                    end_line=end_line,
                    end_column=end_col,
                    coverage_hits=rec.hit_count,
                    calls=fn.calls,
                )

        return _merge_coverages_for_offsets(cov_data)

    def get_ide_function_calls_coverage(
        self,
    ) -> Dict[Tuple[Tuple[int, int], Tuple[int, int]], IdeCoverageRecord]:
        """
        Returns a list of IdeCoverageRecord for each function
        """

        fns_max_calls = max([fn.calls for fn in self.functions.values()])

        cov_data = {}
        for fn in self.functions.values():
            (start_line, start_col), (end_line, end_col) = fn.name_location.ide_pos
            cov_data[fn.name_location.ide_pos] = IdeCoverageRecord(
                start_line=start_line,
                start_column=start_col,
                end_line=end_line,
                end_column=end_col,
                coverage_hits=fn.calls,
                calls=fns_max_calls,
            )
        return _merge_coverages_for_offsets(cov_data)

    def get_ide_modifier_calls_coverage(
        self,
    ) -> Dict[Tuple[Tuple[int, int], Tuple[int, int]], IdeCoverageRecord]:
        """
        Returns a list of IdeCoverageRecord as a dict for each modifier
        """

        cov_data = {}

        for fn in self.functions.values():
            for pc, rec in fn.modifier_cov.items():
                (start_line, start_col), (end_line, end_col) = fn.modifiers[
                    rec.modifier_fn_name
                ].ide_pos

                cov_data[
                    fn.modifiers[rec.modifier_fn_name].ide_pos
                ] = IdeCoverageRecord(
                    start_line=start_line,
                    start_column=start_col,
                    end_line=end_line,
                    end_column=end_col,
                    coverage_hits=rec.hit_count,
                    calls=fn.calls,
                )
        return _merge_coverages_for_offsets(cov_data)

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
                            self.functions[mod_push.fn_name],
                            allowed_fns,
                        )
                        logger.debug(
                            f"Adding {mod_push_pc} to coverage of {parent_fn.modifier_cov}"
                        )
            act_pc = act_pc + act_instr.size

    def _add_modifier_coverage(self):
        for fn in self.functions.values():
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
                if function_def.source[int_to - function_def.byte_location[0] - 1] in (
                    "{",
                    "}",
                ):
                    if len(spaces_intervals[int_to - 1]) != 0:
                        int_to = list(spaces_intervals[int_to - 1])[0].begin
                    else:
                        int_to -= 1
                    changed = True
                if (
                    function_def.source[
                        int_to
                        - function_def.byte_location[0]
                        - 4 : int_to
                        - function_def.byte_location[0]
                    ]
                    == "else"
                ):
                    if len(spaces_intervals[int_to - 4]) != 0:
                        int_to = list(spaces_intervals[int_to - 4])[0].begin
                    else:
                        int_to -= 4
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
            fn = self.functions[fn_def.canonical_name]
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
                self.functions[rec.fn_name].instruction_cov[pc] = cov
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
    Dict[pathlib.Path, IntervalTree],
    Dict[bytes, Dict[int, pathlib.Path]],
    Dict[pathlib.Path, SourceUnit],
    Dict[pathlib.Path, bytes],
]:
    processed_files: Set[pathlib.Path] = set()
    reference_resolver = ReferenceResolver()

    interval_trees: Dict[pathlib.Path, IntervalTree] = {}
    interval_trees_indexes: Dict[bytes, Dict[int, pathlib.Path]] = {}
    source_units: Dict[pathlib.Path, SourceUnit] = {}
    paths_to_cu: Dict[pathlib.Path, bytes] = {}

    for cu, output in outputs:
        for source_unit_name, info in output.sources.items():
            path = cu.source_unit_name_to_path(pathlib.PurePath(source_unit_name))
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
                output.contracts[source_unit_name]
                if source_unit_name in output.contracts
                else None,
            )
            source_units[path] = SourceUnit(init, ast)
            if cu.hash not in interval_trees_indexes:
                interval_trees_indexes[cu.hash] = {}

            interval_trees_indexes[cu.hash][info.id] = path
            paths_to_cu[path] = cu.hash

    reference_resolver.run_post_process_callbacks(
        CallbackParams(interval_trees=interval_trees, source_units=source_units)
    )

    return interval_trees, interval_trees_indexes, source_units, paths_to_cu


def _compile_project(
    config: Optional[WokeConfig] = None,
) -> List[Tuple[CompilationUnit, SolcOutput]]:
    if config is None:
        config = woke.config.WokeConfig()
        config.load_configs()

    sol_files: Set[pathlib.Path] = set()
    for file in config.project_root_path.rglob("**/*.sol"):
        if (
            not any(is_relative_to(file, p) for p in config.compiler.solc.ignore_paths)
            and file.is_file()
        ):
            sol_files.add(file)

    compiler = woke.compile.SolidityCompiler(config)
    outputs: List[Tuple[CompilationUnit, SolcOutput]] = asyncio.run(
        compiler.compile(
            sol_files,
            [SolcOutputSelectionEnum.ALL],
            write_artifacts=False,
            reuse_latest_artifacts=True,
            maximize_compilation_units=True,
        )
    )

    for _, output in outputs:
        for error in output.errors:
            if error.severity == SolcOutputErrorSeverityEnum.ERROR:
                if error.formatted_message is not None:
                    raise Exception(f"Error compiling\n{error.formatted_message}")
                else:
                    raise Exception(f"Error compiling\n{error.message}")

    return outputs


def _parse_source_map(
    interval_trees: Dict[pathlib.Path, IntervalTree],
    interval_tree_indexes: Dict[int, pathlib.Path],
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

        if last_data[2] not in interval_tree_indexes:
            logger.debug(
                f"PC skipped because source file with id {last_data[2]} is not indexed"
            )
            continue

        source_interval = (last_data[0], last_data[0] + last_data[1], last_data[2])
        if fn_changed:
            if source_interval in name_cache:
                last_fn = name_cache[source_interval]
            else:
                interval_tree = interval_trees[interval_tree_indexes[last_data[2]]]
                last_fn = _find_fn_for_source(
                    interval_tree, source_interval[0], source_interval[1]
                )
            name_cache[source_interval] = last_fn

        if last_fn:
            pc_map[pc] = SourceMapPcRecord(
                last_fn,
                (source_interval[0], source_interval[1]),
                source_interval[2],
                last_data[3],
                op,
                argument,
                size,
            )
        logger.debug(f"{pc} {i} {source_interval}, {last_fn}, {fn_changed}")

    return pc_map


def _get_line_intervals(source: str) -> IntervalTree:
    location = 0
    intervals = set()
    for line_num, line in enumerate(source.splitlines(keepends=True)):
        intervals.add((location, location + len(line), line_num))
        location += len(line)
    return IntervalTree.from_tuples(intervals)


def _construct_coverage_data(
    config: Optional[WokeConfig] = None,
) -> Dict[str, ContractCoverage]:
    outputs = _compile_project(config)
    interval_trees, interval_trees_indexes, source_units, paths_to_cu = _parse_project(
        outputs
    )
    contracts_cov = {}

    for unit_path, source_unit in source_units.items():
        cu_hash = paths_to_cu[unit_path]
        line_intervals = _get_line_intervals(source_unit.file.read_text())
        for contract in source_unit.contracts:
            assert contract.compilation_info is not None
            assert contract.compilation_info.evm is not None
            assert contract.compilation_info.evm.deployed_bytecode is not None
            assert contract.compilation_info.evm.deployed_bytecode.opcodes is not None
            assert (
                contract.compilation_info.evm.deployed_bytecode.source_map is not None
            )

            opcodes = contract.compilation_info.evm.deployed_bytecode.opcodes
            source_map = contract.compilation_info.evm.deployed_bytecode.source_map

            logger.debug(f"{contract.name} Opcodes {opcodes}")
            pc_op_map = _parse_opcodes(opcodes)
            logger.debug(f"{contract.name} Pc Op Map {pc_op_map}")
            pc_map = _parse_source_map(
                interval_trees, interval_trees_indexes[cu_hash], source_map, pc_op_map
            )
            logger.debug(f"{contract.name} Pc Map {pc_map}")

            contract_fqn = f"{source_unit.source_unit_name}:{contract.name}"
            contracts_cov[contract_fqn] = ContractCoverage(
                pc_map, contract, line_intervals
            )
    return contracts_cov


def _merge_coverages_for_files(
    coverages_for_files: Dict[
        str, List[Dict[Tuple[Tuple[int, int], Tuple[int, int]], IdeCoverageRecord]]
    ]
) -> Dict[str, Dict[Tuple[Tuple[int, int], Tuple[int, int]], IdeCoverageRecord]]:
    merged_coverages = {}
    for file, coverages in coverages_for_files.items():
        merged_coverages[file] = {}
        for coverage in coverages:
            for (start, end), record in coverage.items():
                if (start, end) in merged_coverages[file]:
                    merged_coverages[file][(start, end)] += record
                else:
                    merged_coverages[file][(start, end)] = record
    return merged_coverages


def _merge_coverages_for_offsets(
    coverages: Dict[Tuple[Tuple[int, int], Tuple[int, int]], IdeCoverageRecord]
) -> Dict[Tuple[Tuple[int, int], Tuple[int, int]], IdeCoverageRecord]:
    merged_coverages = {}
    for (start, end), record in coverages.items():
        if (start, end) in merged_coverages:
            merged_coverages[(start, end)] += record
        else:
            merged_coverages[(start, end)] = record
    return merged_coverages


class Coverage:
    contracts_cov: Dict[str, ContractCoverage]
    contracts_per_trans_cov: Dict[str, ContractCoverage]

    def __init__(self, config: Optional[WokeConfig] = None):
        cov = _construct_coverage_data(config)
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
        self, contract_fqn: str, per_transaction: bool
    ) -> ContractCoverage:
        """
        Returns ContractCoverage for given contract name
        """
        if per_transaction:
            return self.contracts_per_trans_cov[contract_fqn]
        return self.contracts_cov[contract_fqn]

    def get_contract_ide_coverage(
        self, per_transaction: bool
    ) -> Dict[str, List[Dict[str, List]]]:
        """
        Returns dictionary where key is an absolute filepath and values are coverage data for IDE
        """

        coverages = {}

        for name, cov in (
            self.contracts_per_trans_cov.items()
            if per_transaction
            else self.contracts_cov.items()
        ):
            if cov.filename not in coverages:
                coverages[cov.filename] = []

            coverages[cov.filename].append(cov.get_ide_branch_coverage())
            coverages[cov.filename].append(cov.get_ide_function_calls_coverage())
            coverages[cov.filename].append(cov.get_ide_modifier_calls_coverage())

        ret = {}
        for filename, cov_records in _merge_coverages_for_files(coverages).items():
            if filename not in ret:
                ret[filename] = []
            for _, record in cov_records.items():
                ret[filename].append(
                    {
                        "startLine": record.start_line,
                        "startColumn": record.start_column,
                        "endLine": record.end_line,
                        "endColumn": record.end_column,
                        "coverage": f"{int((record.coverage_hits / record.calls) * 100) if record.calls != 0 else 0}",
                        "coverageHits": record.coverage_hits,
                        "message": f"Execs: {record.coverage_hits} / {record.calls}",
                    }
                )

        return ret

    def process_trace(self, contract_fqn: str, trace: Dict[str, Any]):
        """
        Processes debug_traceTransaction and it's struct_logs
        """
        contract_fqn_stack = [contract_fqn]
        transaction_fqn_pcs = set()

        for struct_log in trace["structLogs"]:
            last_fqn = contract_fqn_stack[-1]
            pc = int(struct_log["pc"])
            if struct_log["op"] in ("CALL", "CALLCODE", "DELEGATECALL", "STATICCALL"):
                logger.debug(f"Call {pc} {struct_log['op']} {struct_log['stack']}")
                addr = Address(int(struct_log["stack"][-2], 16))
                new_fqn = get_fqn_from_address(addr, default_chain)
                if new_fqn is None:
                    new_fqn = "Unknown"
                contract_fqn_stack.append(new_fqn)
            elif (
                struct_log["op"] in ("RETURN", "STOP", "REVERT")
                and len(contract_fqn_stack) > 1
            ):
                logger.debug(f"{pc} {struct_log['op']} before pop {contract_fqn_stack}")
                contract_fqn_stack.pop()

            if (
                last_fqn not in self.contracts_cov
                or last_fqn not in self.contracts_per_trans_cov
            ):
                continue

            contract_cov = self.contracts_cov[last_fqn]
            contract_cov_per_trans = self.contracts_per_trans_cov[last_fqn]
            if pc in contract_cov.pc_map:
                logger.debug(
                    f"{pc} {struct_log['op']} {contract_cov.pc_map[pc].op} "
                    f"{contract_cov.pc_map[pc].argument} "
                    f"from {contract_cov.pc_map[pc].fn_name} {contract_cov.pc_map[pc].offset} is "
                    f"executed "
                )
            else:
                logger.debug(f"{pc} {struct_log['op']} is executed ")

            if (last_fqn, pc) not in transaction_fqn_pcs:
                transaction_fqn_pcs.add((last_fqn, pc))
                contract_cov_per_trans.add_cov(pc)
            contract_cov.add_cov(pc)


class CoverageProvider:
    _dev_chain: DevChainABC
    _coverage: Coverage
    _next_block_to_cover: int

    def __init__(
        self,
        coverage: Coverage,
        starter_block: Optional[int] = None,
    ):
        self._dev_chain = default_chain.dev_chain
        self._coverage = coverage
        self._next_block_to_cover = starter_block if starter_block is not None else 0

    def get_coverage(self) -> Coverage:
        return self._coverage

    def update_coverage(self):
        """
        Checks for latest transactions on blockchain for
        """
        last_block = self._dev_chain.get_block_number()
        if (
            self._next_block_to_cover >= last_block
        ):  # chain was reset -> reset last_covered_block
            self._next_block_to_cover = 0

        for block_number in range(self._next_block_to_cover, last_block + 1):
            logger.debug("Working on block %d", block_number)
            block_info = self._dev_chain.get_block(block_number, True)
            logger.debug(block_info["transactions"])
            for transaction in block_info["transactions"]:
                if "to" not in transaction or transaction["to"] is None:
                    assert "input" in transaction
                    bytecode = transaction["input"]
                    if bytecode.startswith("0x"):
                        bytecode = bytecode[2:]
                    bytecode = bytes.fromhex(bytecode)
                    contract_fqn = get_fqn_from_deployment_code(bytecode)
                    logger.info(f"Contract {contract_fqn} was deployed")
                else:
                    contract_fqn = get_fqn_from_address(
                        Address(transaction["to"]), default_chain
                    )
                    assert (
                        contract_fqn is not None
                    ), f"Contract not found for {transaction['to']}"

                trace = self._dev_chain.debug_trace_transaction(
                    transaction["hash"],
                    {
                        "disableMemory": True,
                        "disableStack": False,
                        "disableStorage": True,
                    },
                )
                self._coverage.process_trace(contract_fqn, trace)
        self._next_block_to_cover = last_block + 1


def get_merged_ide_coverage(
    coverages: List[Coverage],
) -> Optional[
    Tuple[Dict[str, List[Dict[str, List]]], Dict[str, List[Dict[str, List]]]]
]:
    """
    Returns both not per transaction and per transaction merged coverages for IDE
    """

    if len(coverages) < 0:
        return None
    cov = copy.deepcopy(coverages[0])
    for c in coverages[1:]:
        cov += c
    return cov.get_contract_ide_coverage(False), cov.get_contract_ide_coverage(True)
