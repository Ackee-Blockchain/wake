import asyncio
import copy
import logging
import pathlib
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from intervaltree import IntervalTree

import woke.compiler
import woke.config
from woke.ast.enums import FunctionKind, GlobalSymbolsEnum
from woke.ast.ir.abc import IrAbc
from woke.ast.ir.declaration.abc import DeclarationAbc
from woke.ast.ir.declaration.contract_definition import ContractDefinition
from woke.ast.ir.declaration.function_definition import FunctionDefinition
from woke.ast.ir.declaration.modifier_definition import ModifierDefinition
from woke.ast.ir.expression.function_call import FunctionCall
from woke.ast.ir.meta.source_unit import SourceUnit
from woke.ast.ir.reference_resolver import CallbackParams, ReferenceResolver
from woke.ast.ir.statement.abc import StatementAbc
from woke.ast.ir.statement.block import Block
from woke.ast.ir.statement.break_statement import Break
from woke.ast.ir.statement.continue_statement import Continue
from woke.ast.ir.statement.do_while_statement import DoWhileStatement
from woke.ast.ir.statement.expression_statement import ExpressionStatement
from woke.ast.ir.statement.for_statement import ForStatement
from woke.ast.ir.statement.if_statement import IfStatement
from woke.ast.ir.statement.inline_assembly import InlineAssembly
from woke.ast.ir.statement.placeholder_statement import PlaceholderStatement
from woke.ast.ir.statement.return_statement import Return
from woke.ast.ir.statement.revert_statement import RevertStatement
from woke.ast.ir.statement.while_statement import WhileStatement
from woke.ast.ir.utils import IrInitTuple
from woke.ast.ir.yul.abc import YulAbc
from woke.ast.ir.yul.block import Block as YulBlock
from woke.ast.ir.yul.break_statement import Break as YulBreak
from woke.ast.ir.yul.continue_statement import Continue as YulContinue
from woke.ast.ir.yul.expression_statement import (
    ExpressionStatement as YulExpressionStatement,
)
from woke.ast.ir.yul.for_loop import ForLoop as YulForLoop
from woke.ast.ir.yul.function_call import FunctionCall as YulFunctionCall
from woke.ast.ir.yul.if_statement import If as YulIf
from woke.ast.ir.yul.leave import Leave as YulLeave
from woke.ast.ir.yul.switch import Switch as YulSwitch
from woke.compiler.build_data_model import ProjectBuild
from woke.compiler.solc_frontend import (
    SolcOutputError,
    SolcOutputErrorSeverityEnum,
    SolcOutputSelectionEnum,
)
from woke.config import WokeConfig
from woke.testing import default_chain
from woke.testing.chain_interfaces import ChainInterfaceAbc
from woke.testing.core import (
    Address,
    get_fqn_from_address,
    get_fqn_from_deployment_code,
)
from woke.utils.file_utils import is_relative_to

logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)


@dataclass
class SourceMapPcRecord:
    fn_ident: str
    offset: Tuple[int, int]
    source_id: int
    jump_type: str
    mod_depth: Optional[int]
    op: str
    argument: Optional[int]
    size: int


@dataclass(frozen=True, eq=True)
class IdePosition:
    start_line: int
    start_column: int
    end_line: int
    end_column: int

    def __iter__(self):
        yield self.start_line
        yield self.start_column
        yield self.end_line
        yield self.end_column


def _get_line_col_from_offset(
    location: int, line_intervals: IntervalTree
) -> Tuple[int, int]:
    if len(line_intervals[location]) != 1:
        logger.debug(f"Getting location for {location} in {line_intervals}")
        raise IndexError(f"No or too many line intervals for {location}")
    interval = list(line_intervals[location])[0]
    return interval.data, location - interval.begin


class LocationInfo:
    byte_offsets: Tuple[int, int]
    file_path: pathlib.Path
    ide_pos: IdePosition

    def __init__(
        self,
        byte_location: Tuple[int, int],
        filename: pathlib.Path,
        line_intervals: IntervalTree,
    ):
        self.byte_offsets = byte_location
        self.file_path = filename
        self.ide_pos = IdePosition(
            *_get_line_col_from_offset(byte_location[0], line_intervals),
            *_get_line_col_from_offset(byte_location[1], line_intervals),
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
    modifier_fn_ident: str


def _get_fn_ident(definition: DeclarationAbc) -> str:
    lines = definition.declaration_string.splitlines()
    if len(lines) > 0:
        ident = lines[-1]
    else:
        ident = definition.declaration_string
    if isinstance(definition.parent, ContractDefinition):
        ident = f"{definition.parent.canonical_name}:{ident}"
    return ident


@dataclass
class FunctionInfo:
    ident: str
    name_location: LocationInfo
    body_location: Optional[LocationInfo]
    modifiers: Dict[str, LocationInfo]
    instruction_cov: Dict[int, InstrCovRecord]
    branch_cov: Dict[int, BranchCovRecord]
    first_branches_cov: List[BranchCovRecord]
    modifier_cov: Dict[int, ModifierCovRecord]
    modifiers_pcs: Dict[str, Tuple[int, int]]
    fn_type: type
    constructor_mods: Set[str]

    def __init__(
        self,
        fn_def: Union[FunctionDefinition, ModifierDefinition],
        line_intervals: IntervalTree,
    ):
        self.ident = _get_fn_ident(fn_def)
        self.fn_type = (
            FunctionDefinition
            if isinstance(fn_def, FunctionDefinition)
            else ModifierDefinition
        )
        self.name_location = LocationInfo(
            fn_def.name_location, fn_def.file, line_intervals
        )
        self.constructor_mods = set()

        self.body_location = (
            LocationInfo(fn_def.body.byte_location, fn_def.file, line_intervals)
            if fn_def.body
            else None
        )

        self.modifiers = {}
        if isinstance(fn_def, FunctionDefinition):
            for mod in fn_def.modifiers:
                if not isinstance(
                    mod.modifier_name.referenced_declaration, GlobalSymbolsEnum
                ):
                    if isinstance(
                        mod.modifier_name.referenced_declaration, ContractDefinition
                    ):
                        constructors = [
                            f
                            for f in mod.modifier_name.referenced_declaration.functions
                            if f.kind == FunctionKind.CONSTRUCTOR
                        ]
                        assert len(constructors) == 1
                        mod_ref_decl = constructors[0]
                    else:
                        mod_ref_decl = mod.modifier_name.referenced_declaration

                    self.modifiers[_get_fn_ident(mod_ref_decl)] = LocationInfo(
                        mod.byte_location, fn_def.file, line_intervals
                    )
                    if (
                        isinstance(mod_ref_decl, FunctionDefinition)
                        and mod_ref_decl.kind == FunctionKind.CONSTRUCTOR
                    ):
                        self.constructor_mods.add(_get_fn_ident(mod_ref_decl))

        self.modifiers_pcs = {}
        self.instruction_cov = {}
        self.branch_cov = {}
        self.modifier_cov = {}
        self.first_branches_cov = []

    @property
    def calls(self):
        if len(self.first_branches_cov) == 0 and len(self.modifier_cov) == 0:
            if len(self.instruction_cov) > 0:
                return self.instruction_cov[min(self.instruction_cov.keys())].hit_count
            else:
                return 0
        return max(
            sum([x.hit_count for x in self.first_branches_cov]),
            max([x.hit_count for x in self.modifier_cov.values()])
            if len(self.modifier_cov) > 0
            else 0,
        )


@dataclass
class IdeCoverageRecord:
    ide_pos: IdePosition
    coverage_hits: int

    def __add__(self, other):
        self.coverage_hits += other.coverage_hits
        return self

    def export(self):
        """
        Exports record in a dictionary for IDE coverage
        """
        return {
            "startLine": self.ide_pos.start_line,
            "startColumn": self.ide_pos.start_column,
            "endLine": self.ide_pos.end_line,
            "endColumn": self.ide_pos.end_column,
            "coverageHits": self.coverage_hits,
        }


@dataclass
class IdeFunctionCoverageRecord(IdeCoverageRecord):
    name: str
    mod_records: Dict[IdePosition, IdeCoverageRecord]
    branch_records: Dict[IdePosition, IdeCoverageRecord]

    def __add__(self, other):
        self.coverage_hits += other.coverage_hits
        for pos, rec in other.mod_records.items():
            if pos in self.mod_records:
                self.mod_records[pos] += rec
            else:
                self.mod_records[pos] = copy.deepcopy(rec)
        for pos, rec in other.branch_records.items():
            if pos in self.branch_records:
                self.branch_records[pos] += rec
            else:
                self.branch_records[pos] = copy.deepcopy(rec)
        return self

    def export(self):
        """
        Exports record in a dictionary for IDE coverage
        """
        return {
            "name": self.name,
            "startLine": self.ide_pos.start_line,
            "startColumn": self.ide_pos.start_column,
            "endLine": self.ide_pos.end_line,
            "endColumn": self.ide_pos.end_column,
            "coverageHits": self.coverage_hits,
            "modRecords": [v.export() for v in self.mod_records.values()],
            "branchRecords": [v.export() for v in self.branch_records.values()],
        }


def _find_code_spaces_intervals(source_code: str) -> IntervalTree:
    in_interval = False
    int_start = 0
    intervals = set()
    for i, c in enumerate(source_code):
        if c in (" ", "\t", "\n", "\r"):
            if not in_interval:
                int_start = i
                in_interval = True
        elif in_interval:
            intervals.add((int_start, i + 1))
            in_interval = False
    return IntervalTree.from_tuples(intervals)


def _get_full_source(node: IrAbc) -> str:
    if isinstance(node, SourceUnit):
        return node.file_source.decode("utf-8")
    if node.parent is None:
        raise ValueError(f"Node {node} has no parent")
    return _get_full_source(node.parent)


class ContractCoverage:
    pc_map: Dict[int, SourceMapPcRecord]
    pc_function: Dict[int, FunctionInfo]
    pc_instruction_cov: Dict[int, InstrCovRecord]
    pc_branch_cov: Dict[int, BranchCovRecord]
    pc_modifier_cov: Dict[int, ModifierCovRecord]
    functions: Dict[str, FunctionInfo]

    def __init__(
        self,
        pc_map: Dict[int, SourceMapPcRecord],
        pc_fn_def_map: Dict[int, Union[FunctionDefinition, ModifierDefinition]],
        contract_def: ContractDefinition,
    ):
        self.pc_map = pc_map
        self.pc_instruction_cov = {}
        self.pc_branch_cov = {}
        self.pc_modifier_cov = {}
        self.pc_function = {}
        self.file_path = pathlib.Path(contract_def.file.absolute())
        self.functions = {}
        fn_defs = {}

        for pc, rec in self.pc_map.items():
            if rec.fn_ident not in self.functions:
                fn_line_intervals = _get_line_intervals(
                    _get_full_source(pc_fn_def_map[pc])
                )
                fn_info = FunctionInfo(pc_fn_def_map[pc], fn_line_intervals)
                self.functions[rec.fn_ident] = fn_info
                fn_defs[rec.fn_ident] = pc_fn_def_map[pc]

        self._add_instruction_coverage()
        for rec in self.functions.values():
            self._add_modifier_coverage(rec)
            self._add_branch_coverage(rec, fn_defs[rec.ident])

        for pc, rec in self.pc_map.items():
            self.pc_function[pc] = self.functions[rec.fn_ident]

    def add_cov(self, pc: int):
        for cov in [self.pc_branch_cov, self.pc_modifier_cov, self.pc_instruction_cov]:
            if pc in cov:
                cov[pc].hit_count += 1

    def get_ide_coverage(
        self,
    ) -> Dict[pathlib.Path, Dict[IdePosition, IdeFunctionCoverageRecord]]:
        """
        Returns coverage for covered functions (per path) with calls, modifier and branch coverages
        """
        cov_data = {}
        for fn_ident, fn in self.functions.items():
            fp = fn.name_location.file_path
            if fp not in cov_data:
                cov_data[fp] = {}

            mod_records = {}
            for pc, rec in fn.modifier_cov.items():
                mod = fn.modifiers[rec.modifier_fn_ident]
                if mod.ide_pos not in mod_records:
                    mod_records[mod.ide_pos] = IdeCoverageRecord(
                        mod.ide_pos, rec.hit_count
                    )
                else:
                    mod_records[mod.ide_pos] += rec.hit_count

            branch_records = {}
            for pc, rec in fn.branch_cov.items():
                if rec.branch.ide_pos not in branch_records:
                    branch_records[rec.branch.ide_pos] = IdeCoverageRecord(
                        rec.branch.ide_pos, rec.hit_count
                    )
                else:
                    branch_records[rec.branch.ide_pos].coverage_hits += rec.hit_count

            cov_data[fp][fn.name_location.ide_pos] = IdeFunctionCoverageRecord(
                name=fn_ident,
                ide_pos=fn.name_location.ide_pos,
                coverage_hits=fn.calls,
                mod_records=mod_records,
                branch_records=branch_records,
            )

        return cov_data

    def _find_modifier_call(
        self,
        starting_pc: int,
        parent_fn: FunctionInfo,
        caller_fn: FunctionInfo,
        modifier_fns: List[str],
    ):

        starting_instr = self.pc_map[starting_pc]
        act_pc = starting_pc
        logger.debug(
            f"Searching for modifier call from {parent_fn.ident} called by {caller_fn.ident} at {starting_pc} in {starting_instr.fn_ident}"
        )

        scan = True
        while scan:
            if act_pc not in self.pc_map:
                logger.warning(f"PC {act_pc} is not in pc_map")
                break
            act_instr = self.pc_map[act_pc]
            logger.debug(
                f"Act instr: {act_pc} {act_instr.fn_ident} {act_instr.op} {act_instr.argument} {act_instr.fn_ident} {starting_instr.fn_ident}"
            )
            if (
                act_instr.fn_ident is None
                or act_instr.fn_ident != starting_instr.fn_ident
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
                if (
                    jumpdest
                    and jumpdest.src_pc_map.op == "JUMPDEST"
                    and act_instr.argument is not None
                ):
                    for i in range(20):
                        mod_push_pc = act_instr.argument + i
                        mod_push = (
                            self.pc_map[mod_push_pc]
                            if mod_push_pc in self.pc_map
                            else None
                        )

                        if (
                            mod_push
                            and mod_push.fn_ident != act_instr.fn_ident
                            and mod_push.fn_ident in modifier_fns
                        ):
                            if len(parent_fn.modifier_cov) == len(parent_fn.modifiers):
                                scan = False
                                break
                            if mod_push.fn_ident in {
                                m.modifier_fn_ident
                                for m in parent_fn.modifier_cov.values()
                            }:
                                break
                            mod_cov = ModifierCovRecord(
                                hit_count=0, modifier_fn_ident=mod_push.fn_ident
                            )
                            self.pc_modifier_cov[mod_push_pc] = mod_cov
                            parent_fn.modifier_cov[mod_push_pc] = mod_cov
                            logger.debug(
                                f"Added {mod_push_pc} of {mod_cov} to coverage of {parent_fn.modifier_cov}"
                            )

                            if len(parent_fn.modifier_cov) != len(parent_fn.modifiers):
                                self._find_modifier_call(
                                    mod_push_pc,
                                    parent_fn,
                                    self.functions[mod_push.fn_ident],
                                    modifier_fns,
                                )
                            else:
                                scan = False
                            break
            act_pc = act_pc + act_instr.size

    def _find_constructors(
        self,
        starting_pc: int,
        const_ident: str,
        parent_fn: FunctionInfo,
        allowed_fns: List[str],
    ):
        const_pc = starting_pc
        logger.debug(
            f"Searching for constructor {const_ident} in {parent_fn.ident} at {starting_pc}"
        )
        while True:
            if const_pc not in self.pc_map:
                logger.warning(f"PC {const_pc} is not in pc_map")
                break
            act_fn_ident = self.pc_map[const_pc].fn_ident
            if (
                const_pc in self.pc_map
                and act_fn_ident != const_ident
                and act_fn_ident in allowed_fns
                or act_fn_ident == parent_fn.ident
            ):
                if const_ident not in [
                    m.modifier_fn_ident for m in parent_fn.modifier_cov.values()
                ]:
                    const_cov = ModifierCovRecord(
                        hit_count=0, modifier_fn_ident=const_ident
                    )
                    logger.debug(
                        f"Added constructor coverage {starting_pc} {const_ident}, stopped at {const_pc} {act_fn_ident}"
                    )
                    self.pc_modifier_cov[starting_pc] = const_cov
                    parent_fn.modifier_cov[starting_pc] = const_cov

                if act_fn_ident in allowed_fns:
                    self._find_constructors(
                        const_pc, act_fn_ident, parent_fn, allowed_fns
                    )
                break
            if const_pc not in self.pc_map or act_fn_ident not in allowed_fns:
                break
            const_pc = const_pc + self.pc_map[const_pc].size

    def _add_modifier_coverage(self, fn: FunctionInfo):
        if len(fn.modifiers) == 0:
            return

        for pc, rec in self.pc_map.items():
            logger.debug(f"PC {pc} {rec.op} {rec.argument} {rec.fn_ident}")

        fn_modifier_constructors = [name for name in fn.constructor_mods]
        logger.debug(f"Adding modifier coverage for {fn.ident}")
        for pc, rec in fn.instruction_cov.items():
            next_pc = pc + rec.src_pc_map.size
            if (
                rec.src_pc_map.op.startswith("PUSH")
                and next_pc in fn.instruction_cov
                and fn.instruction_cov[next_pc].src_pc_map.op.startswith("JUMP")
            ):
                logger.debug(f"Found jump from {pc} to {next_pc} in {fn.ident}")
                self._find_modifier_call(pc, fn, fn, list(fn.modifiers.keys()))

            if (
                next_pc in self.pc_map
                and self.pc_map[next_pc].fn_ident != fn.ident
                and self.pc_map[next_pc].fn_ident in fn_modifier_constructors
            ):
                logger.debug(f"Found constructor from {pc} to {next_pc} in {fn.ident}")
                self._find_constructors(
                    next_pc, self.pc_map[next_pc].fn_ident, fn, fn_modifier_constructors
                )

        logger.debug(f"Modifiers: {fn.ident} {fn.modifiers} {fn.modifier_cov.keys()}")
        for pc in fn.modifier_cov.keys():
            new_pc = pc
            logger.debug(f"PC: {pc} {self.pc_map[pc].op} {self.pc_map[pc].fn_ident}")
            while True:
                if new_pc not in self.pc_map or self.pc_map[new_pc].fn_ident not in (
                    *fn.modifiers.keys(),
                    fn.ident,
                ):
                    break
                new_pc = new_pc + self.pc_map[new_pc].size
            fn.modifiers_pcs[fn.modifier_cov[pc].modifier_fn_ident] = (pc, new_pc)
        logger.debug(f"Modifier PCs: {fn.ident} {fn.modifiers_pcs}")
        if len(fn.modifiers_pcs) != len(fn.modifiers):
            logging.warning(
                f"PCs were not found for all modifiers for {fn.ident}. "
                f"Try compiling without optimizations"
            )

    def _append_branch(
        self, stmt: IrAbc, parent_statement: IrAbc, branches: Set[Tuple[int, int]]
    ):
        stmt_to = stmt.byte_location[1] - stmt.byte_location[0]
        if parent_statement.source[stmt_to - 1] in ("{", "}"):
            stmt_to -= 1
        stmt_loc_data = (
            stmt.byte_location[0],
            stmt_to,
        )

        branches.add(stmt_loc_data)
        logger.debug(
            f"Added {stmt.file.name} {stmt.byte_location} {stmt.source[:stmt_to]}"
        )

    def _find_assembly_branches(
        self,
        statement: Union[YulAbc, InlineAssembly, YulBlock],
        branches: Set[Tuple[int, int]],
    ):
        append_next = True
        stmts = (
            [statement] if not isinstance(statement, YulBlock) else statement.statements
        )
        for stmt in stmts:
            if append_next:
                self._append_branch(stmt, statement, branches)
                append_next = False

            if isinstance(stmt, YulIf) or isinstance(stmt, YulForLoop):
                self._find_assembly_branches(stmt.body, branches)
                append_next = True
            elif isinstance(stmt, YulSwitch):
                for case in stmt.cases:
                    self._find_assembly_branches(case.body, branches)
            elif (
                isinstance(stmt, YulBreak)
                or isinstance(stmt, YulContinue)
                or isinstance(stmt, YulLeave)
            ):
                append_next = True
            elif isinstance(stmt, YulExpressionStatement) and isinstance(
                stmt.expression, YulFunctionCall
            ):
                append_next = True
            elif isinstance(stmt, YulBlock):
                self._find_assembly_branches(stmt, branches)

    def _find_branches(
        self, statement: Union[StatementAbc, Block], branches: Set[Tuple[int, int]]
    ):
        append_next = True
        stmts = (
            [statement] if not isinstance(statement, Block) else statement.statements
        )
        for stmt in stmts:
            if append_next:
                self._append_branch(stmt, statement, branches)
                append_next = False

            if isinstance(stmt, IfStatement):
                self._find_branches(stmt.true_body, branches)
                if stmt.false_body:
                    self._find_branches(stmt.false_body, branches)
                append_next = True
            elif (
                isinstance(stmt, WhileStatement)
                or isinstance(stmt, ForStatement)
                or isinstance(stmt, DoWhileStatement)
                and stmt.body is not None
            ):
                self._find_branches(stmt.body, branches)
                append_next = True
            elif isinstance(stmt, ExpressionStatement) and isinstance(
                stmt.expression, FunctionCall
            ):
                append_next = True
            elif (
                isinstance(stmt, PlaceholderStatement)
                or isinstance(stmt, RevertStatement)
                or isinstance(stmt, Return)
                or isinstance(stmt, Continue)
                or isinstance(stmt, Break)
            ):
                append_next = True
            elif isinstance(stmt, InlineAssembly):
                self._find_assembly_branches(stmt.yul_block, branches)
                append_next = True
            elif isinstance(stmt, YulBlock):
                self._find_assembly_branches(stmt, branches)
            else:
                for n in stmt:
                    if isinstance(n, FunctionCall) and isinstance(
                        n.function_called, FunctionDefinition
                    ):
                        append_next = True
                        break

    def _get_function_branches(
        self,
        function_def: Union[FunctionDefinition, ModifierDefinition],
        spaces_intervals: IntervalTree,
    ) -> List[Tuple[int, int]]:
        uniq_branches: Set[Tuple[int, int]] = set()
        if not function_def.body:
            return []
        self._find_branches(function_def.body, uniq_branches)
        branches = list(uniq_branches)
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
            logger.debug(f"Processing branch {branch}")
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
            logger.debug(
                f"Final branches for {_get_fn_ident(function_def)} {branches_fin}"
            )

        return branches_fin

    def _add_branch_coverage(
        self,
        fn_info: FunctionInfo,
        fn_def: Union[FunctionDefinition, ModifierDefinition],
    ):
        if not fn_def.body:
            return
        fn_space_intervals = _find_code_spaces_intervals(_get_full_source(fn_def))
        fn_line_intervals = _get_line_intervals(_get_full_source(fn_def))

        logger.debug(f"Adding branch coverage to {_get_fn_ident(fn_def)}")
        branches = self._get_function_branches(fn_def, fn_space_intervals)
        logger.debug(f"Branches: {branches}")
        logger.debug(f"Modifiers: {fn_info.modifiers}")

        first_branch = True
        for branch in branches:
            branch_loc = LocationInfo(branch, fn_def.file, fn_line_intervals)
            logger.debug(f"Branch: {branch_loc}")
            pcs = set()
            if isinstance(fn_def, ModifierDefinition):
                mods = []
                for f in self.functions.values():
                    for m in f.modifiers.keys():
                        if m == _get_fn_ident(fn_def) and m in f.modifiers_pcs:
                            mods.append(f.modifiers_pcs[m])
                logger.debug(f"Modifiers: {fn_info.ident} {mods}")
                for mod in mods:
                    pcs.add(self._find_branch_pcs(branch, mod))
            else:
                pcs.add(self._find_branch_pcs(branch))
            for pc in pcs:
                if pc is None:
                    logger.debug(f"No pc found")
                    continue
                branch_cov = BranchCovRecord(
                    hit_count=0, src_pc_map=self.pc_map[pc], branch=branch_loc
                )
                self.pc_branch_cov[pc] = branch_cov
                fn_info.branch_cov[pc] = branch_cov
                if first_branch:
                    fn_info.first_branches_cov.append(branch_cov)
            first_branch = False
        logger.debug(
            f"Function {fn_info.ident} has these branch detection instructions: "
            f"{fn_info.branch_cov.keys()} and these first branches: {[x.src_pc_map.op for x in fn_info.first_branches_cov]}"
        )

    def _add_instruction_coverage(self):
        for pc, rec in self.pc_map.items():
            if rec.fn_ident is not None:
                cov = InstrCovRecord(hit_count=0, src_pc_map=rec)

                self.functions[rec.fn_ident].instruction_cov[pc] = cov
                self.pc_instruction_cov[pc] = cov

    def _find_branch_pcs(
        self, source_int: Tuple[int, int], allowed_int: Optional[Tuple[int, int]] = None
    ) -> Optional[int]:
        interval_tree = IntervalTree.from_tuples(
            {
                (rec.offset[0], rec.offset[1], pc)
                for pc, rec in self.pc_map.items()
                if allowed_int is None or (allowed_int[0] <= pc <= allowed_int[1])
            }
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
) -> Optional[FunctionDefinition]:
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
    final_fn = None
    for node in function_def_nodes:
        logger.debug(
            f"{source_from}:{source_to} {len(function_def_nodes)} {str(type(node.data))} {_get_fn_ident(node.data)}"
        )
        overlap = node.overlap_size(source_from, source_to) / node.length()
        logger.debug(f"overlap {overlap} {max_overlap} {source_from}:{source_to}")
        if max_overlap is None or overlap > max_overlap:
            max_overlap = overlap
            final_fn = node.data
    return final_fn


def _compile_project(
    config: Optional[WokeConfig] = None,
) -> ProjectBuild:
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

    compiler = woke.compiler.SolidityCompiler(config)
    compiler.load()

    build: ProjectBuild
    errors: Set[SolcOutputError]
    build, errors = asyncio.run(
        compiler.compile(
            sol_files,
            [SolcOutputSelectionEnum.ALL],
            write_artifacts=False,
        )
    )

    for error in errors:
        if error.severity == SolcOutputErrorSeverityEnum.ERROR:
            if error.formatted_message is not None:
                raise Exception(f"Error compiling\n{error.formatted_message}")
            else:
                raise Exception(f"Error compiling\n{error.message}")

    return build


def _parse_source_map(
    interval_trees: Dict[pathlib.Path, IntervalTree],
    cu_hash: bytes,
    reference_resolver: ReferenceResolver,
    source_map: str,
    pc_op_map: List[Tuple[int, str, int, Optional[int]]],
) -> Tuple[
    Dict[int, SourceMapPcRecord],
    Dict[int, Union[FunctionDefinition, ModifierDefinition]],
]:
    pc_map = {}
    pc_fn_def_map = {}
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

        try:
            reference_resolver.resolve_source_file_id(last_data[2], cu_hash)
        except KeyError:
            logger.debug(
                f"PC skipped because source file with id {last_data[2]} is not indexed"
            )
            continue

        source_interval = (last_data[0], last_data[0] + last_data[1], last_data[2])
        if fn_changed:
            if source_interval in name_cache:
                last_fn = name_cache[source_interval]
            else:
                interval_tree = interval_trees[
                    reference_resolver.resolve_source_file_id(last_data[2], cu_hash)
                ]
                last_fn = _find_fn_for_source(
                    interval_tree, source_interval[0], source_interval[1]
                )
            name_cache[source_interval] = last_fn

        if last_fn:
            pc_map[pc] = SourceMapPcRecord(
                _get_fn_ident(last_fn),
                (source_interval[0], source_interval[1]),
                source_interval[2],
                last_data[3],
                last_data[4],
                op,
                argument,
                size,
            )
            pc_fn_def_map[pc] = last_fn

    return pc_map, pc_fn_def_map


def _get_line_intervals(source: str) -> IntervalTree:
    location = 0
    intervals = set()
    lines = source.splitlines(keepends=True)
    for line_num, line in enumerate(lines):
        location_end = location + len(line)
        if line_num + 1 == len(lines):
            location_end += 1
        intervals.add((location, location_end, line_num))
        location += len(line)
    return IntervalTree.from_tuples(intervals)


def _construct_coverage_data(
    config: Optional[WokeConfig] = None, use_deployed_bytecode: bool = True
) -> Dict[str, ContractCoverage]:
    build = _compile_project(config)
    contracts_cov = {}

    for unit_path, source_unit in build.source_units.items():
        for contract in source_unit.contracts:
            assert contract.compilation_info is not None
            assert contract.compilation_info.evm is not None

            if use_deployed_bytecode:
                bytecode = contract.compilation_info.evm.deployed_bytecode
            else:
                bytecode = contract.compilation_info.evm.bytecode

            assert bytecode is not None
            assert bytecode.opcodes is not None
            assert bytecode.source_map is not None

            opcodes = bytecode.opcodes
            source_map = bytecode.source_map

            logger.debug(f"Processing {contract.name} from {unit_path}")
            logger.debug(f"{contract.name} Opcodes {opcodes}")
            pc_op_map = _parse_opcodes(opcodes)
            logger.debug(f"{contract.name} Pc Op Map {pc_op_map}")
            pc_map, pc_fn_def_map = _parse_source_map(
                build.interval_trees,
                contract.cu_hash,
                build.reference_resolver,
                source_map,
                pc_op_map,
            )
            logger.debug(f"{contract.name} Pc Map {pc_map}")

            contract_fqn = f"{source_unit.source_unit_name}:{contract.name}"
            contracts_cov[contract_fqn] = ContractCoverage(
                pc_map, pc_fn_def_map, contract
            )
    return contracts_cov


class Coverage:
    contracts_cov: Dict[str, ContractCoverage]
    contracts_undeployed_cov: Dict[str, ContractCoverage]
    contracts_per_trans_cov: Dict[str, ContractCoverage]
    contracts_undeployed_per_trans_cov: Dict[str, ContractCoverage]

    def __init__(self, config: Optional[WokeConfig] = None):
        self.contracts_cov = _construct_coverage_data(
            config, use_deployed_bytecode=True
        )
        self.contracts_per_trans_cov = copy.deepcopy(self.contracts_cov)
        self.contracts_undeployed_cov = _construct_coverage_data(
            config, use_deployed_bytecode=False
        )
        self.contracts_undeployed_per_trans_cov = copy.deepcopy(
            self.contracts_undeployed_cov
        )

    def get_contract_ide_coverage(
        self, per_transaction: bool
    ) -> Dict[pathlib.Path, Dict[IdePosition, IdeFunctionCoverageRecord]]:
        """
        Returns coverage data for IDE usage
        """

        funcs_covs = []
        for coverage in (
            (self.contracts_cov, self.contracts_undeployed_cov)
            if not per_transaction
            else (self.contracts_per_trans_cov, self.contracts_undeployed_per_trans_cov)
        ):
            for con_cov in coverage.values():
                funcs_covs.append(con_cov.get_ide_coverage())
        return _merge_ide_function_coverages(funcs_covs)

    def process_trace(
        self, contract_fqn: str, trace: Dict[str, Any], is_from_deployment: bool = False
    ):
        """
        Processes debug_traceTransaction and it's struct_logs
        """
        contract_fqn_stack = [contract_fqn]
        transaction_fqn_pcs = set()
        deployment = is_from_deployment

        for struct_log in trace["structLogs"]:
            last_fqn = contract_fqn_stack[-1]
            pc = int(struct_log["pc"])
            if struct_log["op"] in ("CALL", "CALLCODE", "DELEGATECALL", "STATICCALL"):
                logger.debug(f"Call {pc} {struct_log['op']} {struct_log['stack']}")
                addr = Address(int(struct_log["stack"][-2], 16))
                new_fqn = get_fqn_from_address(addr, "latest", default_chain)  # TODO
                if new_fqn is None:
                    new_fqn = "Unknown"
                contract_fqn_stack.append(new_fqn)
            elif struct_log["op"] in ("CREATE", "CREATE2"):
                logger.debug(f"Call {pc} {struct_log['op']} {struct_log['memory']}")
                offset = int(struct_log["stack"][-2], 16)
                length = int(struct_log["stack"][-3], 16)

                start_block = offset // 32
                start_offset = offset % 32
                end_block = (offset + length) // 32
                end_offset = (offset + length) % 32

                if start_block == end_block:
                    deployment_code = bytes.fromhex(struct_log["memory"][start_block])[
                        start_offset : start_offset + length
                    ]
                else:
                    deployment_code = bytes.fromhex(struct_log["memory"][start_block])[
                        start_offset:
                    ]
                    for i in range(start_block + 1, end_block):
                        deployment_code += bytes.fromhex(struct_log["memory"][i])
                    deployment_code += bytes.fromhex(struct_log["memory"][end_block])[
                        :end_offset
                    ]
                new_fqn, _ = get_fqn_from_deployment_code(
                    deployment_code
                )  # pyright: reportGeneralTypeIssues=false
                contract_fqn_stack.append(new_fqn)
                deployment = True
            elif (
                struct_log["op"] in ("RETURN", "STOP", "REVERT")
                and len(contract_fqn_stack) > 1
            ):
                logger.debug(f"{pc} {struct_log['op']} before pop {contract_fqn_stack}")
                contract_fqn_stack.pop()
                if not is_from_deployment and deployment:
                    deployment = False

            contracts_cov = (
                self.contracts_cov if not deployment else self.contracts_undeployed_cov
            )
            contracts_per_trans_cov = (
                self.contracts_per_trans_cov
                if not deployment
                else self.contracts_undeployed_per_trans_cov
            )
            if last_fqn not in contracts_cov or last_fqn not in contracts_per_trans_cov:
                continue

            contract_cov = contracts_cov[last_fqn]
            contract_cov_per_trans = contracts_per_trans_cov[last_fqn]
            if pc in contract_cov.pc_map:
                logger.debug(
                    f"{pc} {struct_log['op']} {contract_cov.pc_map[pc].op} {contract_cov.pc_map[pc].mod_depth} "
                    f"{contract_cov.pc_map[pc].argument} "
                    f"from {contract_cov.pc_map[pc].fn_ident} {contract_cov.pc_map[pc].offset} is "
                    f"executed "
                )
            else:
                logger.debug(f"{pc} {struct_log['op']} is executed ")

            if (last_fqn, pc) not in transaction_fqn_pcs:
                transaction_fqn_pcs.add((last_fqn, pc))
                contract_cov_per_trans.add_cov(pc)
            contract_cov.add_cov(pc)


class CoverageProvider:
    _chain_interface: ChainInterfaceAbc
    _coverage: Coverage
    _next_block_to_cover: int

    def __init__(
        self,
        coverage: Coverage,
        starter_block: Optional[int] = None,
    ):
        self._chain_interface = default_chain.chain_interface
        self._coverage = coverage
        self._next_block_to_cover = starter_block if starter_block is not None else 0

    def get_coverage(self) -> Coverage:
        return self._coverage

    def update_coverage(self):
        """
        Checks for latest transactions on blockchain and updates coverage
        """
        last_block = self._chain_interface.get_block_number()
        if (
            self._next_block_to_cover > last_block + 1
        ):  # chain was reset -> reset last_covered_block
            self._next_block_to_cover = 0
        for block_number in range(self._next_block_to_cover, last_block + 1):
            logger.debug("Working on block %d", block_number)
            block_info = self._chain_interface.get_block(block_number, True)
            logger.debug(block_info["transactions"])
            for transaction in block_info["transactions"]:
                logger.debug(transaction)

                trace = self._chain_interface.debug_trace_transaction(
                    transaction["hash"],
                    {
                        "enableMemory": True,
                        "enableStack": True,
                        "disableStorage": False,
                    },
                )

                if "to" not in transaction or transaction["to"] is None:
                    assert "input" in transaction
                    bytecode = transaction["input"]
                    if bytecode.startswith("0x"):
                        bytecode = bytecode[2:]
                    bytecode = bytes.fromhex(bytecode)
                    contract_fqn = get_fqn_from_deployment_code(bytecode)

                    self._coverage.process_trace(
                        contract_fqn, trace, is_from_deployment=True
                    )
                    logger.info(f"Contract {contract_fqn} was deployed")
                else:
                    contract_fqn = get_fqn_from_address(
                        Address(transaction["to"]), default_chain
                    )
                    assert (
                        contract_fqn is not None
                    ), f"Contract not found for {transaction['to']}"

                    self._coverage.process_trace(
                        contract_fqn, trace, is_from_deployment=False
                    )
        self._next_block_to_cover = last_block + 1


def _merge_ide_function_coverages(
    func_covs: List[Dict[pathlib.Path, Dict[IdePosition, IdeFunctionCoverageRecord]]]
) -> Dict[pathlib.Path, Dict[IdePosition, IdeFunctionCoverageRecord]]:
    merged = {}

    for func_cov in func_covs:
        for file_path, ide_func_cov_recs in func_cov.items():
            if file_path not in merged:
                merged[file_path] = {}
            for ide_pos, func_cov_rec in ide_func_cov_recs.items():
                if ide_pos not in merged[file_path]:
                    merged[file_path][ide_pos] = copy.deepcopy(func_cov_rec)
                else:
                    merged[file_path][ide_pos] += func_cov_rec
    return merged


def export_merged_ide_coverage(
    func_covs: List[Dict[pathlib.Path, Dict[IdePosition, IdeFunctionCoverageRecord]]]
) -> Dict[str, List[Dict[str, List]]]:
    """
    Merges and exports IDE coverage records into a dictionary of paths -> funcs and their
    coverage records
    """
    merged_records = _merge_ide_function_coverages(func_covs)

    exported_coverage = {}
    for file_path, func_cov_recs in merged_records.items():
        file_path_str = str(file_path)
        if file_path not in exported_coverage:
            exported_coverage[file_path_str] = []
        for ide_pos, func_cov_rec in func_cov_recs.items():
            exported_coverage[file_path_str].append(func_cov_rec.export())
    return exported_coverage
