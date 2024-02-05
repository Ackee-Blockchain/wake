from __future__ import annotations

import copy
import json
import logging
import pathlib
import re
import time
from collections import ChainMap, defaultdict
from dataclasses import asdict, dataclass, field
from itertools import chain
from typing import Any, Callable, DefaultDict, Dict, List, Optional, Set, Tuple, Union

from intervaltree import IntervalTree

from wake.cli.console import console
from wake.compiler import SolidityCompiler
from wake.compiler.build_data_model import ProjectBuild
from wake.config import WakeConfig
from wake.core import get_logger
from wake.development.chain_interfaces import TxParams
from wake.development.core import (
    Address,
    Chain,
    get_fqn_from_address,
    get_fqn_from_creation_code,
)
from wake.development.internal import read_from_memory
from wake.ir import (
    Block,
    DoWhileStatement,
    ForStatement,
    FunctionDefinition,
    IfStatement,
    IrAbc,
    ModifierDefinition,
    SourceUnit,
    StatementAbc,
    TryStatement,
    UncheckedBlock,
    WhileStatement,
    YulBlock,
    YulForLoop,
    YulFunctionDefinition,
    YulIf,
    YulStatementAbc,
    YulSwitch,
)
from wake.ir.reference_resolver import ReferenceResolver

logger = get_logger(__name__, logging.ERROR)


@dataclass
class SourceMapPcRecord:
    offset: Tuple[int, int]
    source_file: Optional[pathlib.Path]
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
    byte_offset: int, line_index: List[Tuple[bytes, int]]
) -> Tuple[int, int]:
    line_num = _binary_search(line_index, byte_offset)
    line_data, prefix_sum = line_index[line_num]
    line_offset = byte_offset - prefix_sum
    return line_num, line_offset


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


def _binary_search(lines: List[Tuple[bytes, int]], x: int) -> int:
    l = 0
    r = len(lines)

    while l < r:
        mid = l + (r - l) // 2
        if lines[mid][1] < x + 1:
            l = mid + 1
        else:
            r = mid

    return l - 1


def _setup_line_indexes(content: bytes) -> List[Tuple[bytes, int]]:
    tmp_lines = re.split(b"(\r?\n)", content)
    lines: List[bytes] = []
    for line in tmp_lines:
        if line in {b"\r\n", b"\n"}:
            lines[-1] += line
        else:
            lines.append(line)

    # UTF-8 encoded lines with prefix length
    encoded_lines: List[Tuple[bytes, int]] = []
    prefix_sum = 0
    for line in lines:
        encoded_lines.append((line, prefix_sum))
        prefix_sum += len(line)
    return encoded_lines


def _parse_opcodes(opcodes: str) -> List[Tuple[int, str, int, Optional[int]]]:
    pc_op_map = []
    opcodes_spl = opcodes.split(" ")

    pc = 0
    ignore = False

    for i, opcode in enumerate(opcodes_spl):
        if ignore:
            ignore = False
            continue

        if not opcode.startswith("PUSH") or opcode == "PUSH0":
            pc_op_map.append((pc, opcode, 1, None))
            pc += 1
        else:
            size = int(opcode[4:]) + 1
            pc_op_map.append((pc, opcode, size, int(opcodes_spl[i + 1], 16)))
            pc += size
            ignore = True
    return pc_op_map


def _parse_source_map(
    cu_hash: bytes,
    reference_resolver: ReferenceResolver,
    source_map: str,
    pc_op_map: List[Tuple[int, str, int, Optional[int]]],
) -> Dict[int, SourceMapPcRecord]:
    pc_map = {}
    source_map_spl = source_map.split(";")

    last_data = [-1, -1, -1, None, None]

    for i, sm_item in enumerate(source_map_spl):
        pc, op, size, argument = pc_op_map[i]
        source_spl = sm_item.split(":")
        for x in range(len(source_spl)):
            if source_spl[x] == "":
                continue
            if x < 3:
                last_data[x] = int(source_spl[x])
            else:
                last_data[x] = source_spl[x]

        source_interval = (last_data[0], last_data[0] + last_data[1], last_data[2])

        try:
            path = reference_resolver.resolve_source_file_id(
                source_interval[2], cu_hash
            )
        except KeyError:
            path = None
        pc_map[pc] = SourceMapPcRecord(
            (source_interval[0], source_interval[1]),
            path,
            last_data[3],
            last_data[4],
            op,
            argument,
            size,
        )

    return pc_map


def _construct_coverage_data(
    build: ProjectBuild, use_deployed_bytecode: bool = True
) -> Dict[str, Dict[int, SourceMapPcRecord]]:
    pc_maps = {}

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
            pc_map = _parse_source_map(
                contract.source_unit.cu_hash,
                build.reference_resolver,
                source_map,
                pc_op_map,
            )
            logger.debug(f"{contract.name} Pc Map {pc_map}")

            contract_fqn = f"{source_unit.source_unit_name}:{contract.name}"
            pc_maps[contract_fqn] = pc_map
    return pc_maps


def merge_ide_function_coverages(
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
    merged_records = merge_ide_function_coverages(func_covs)

    exported_coverage = {}
    for file_path, func_cov_recs in merged_records.items():
        file_path_str = str(file_path)
        if file_path not in exported_coverage:
            exported_coverage[file_path_str] = []
        for ide_pos, func_cov_rec in func_cov_recs.items():
            exported_coverage[file_path_str].append(func_cov_rec.export())
    return exported_coverage


@dataclass
class CoverageFileData:
    version: str = "1.0"
    data: Dict[str, List[Dict[str, List]]] = field(default_factory=dict)


def write_coverage(
    coverage: Dict[str, List[Dict[str, List]]], coverage_file: pathlib.Path
):
    data = CoverageFileData(data=coverage)
    with open(coverage_file, "w") as f:
        json.dump(asdict(data), f, indent=4)


def returning_none():
    return None


class CoverageHandler:
    _pc_maps: Dict[str, Dict[int, SourceMapPcRecord]]
    _pc_maps_undeployed: Dict[str, Dict[int, SourceMapPcRecord]]
    _interval_trees: Dict[pathlib.Path, IntervalTree]
    _lines_index: Dict[pathlib.Path, List[Tuple[bytes, int]]]
    _statement_coverage: DefaultDict[Union[StatementAbc, YulStatementAbc], int]
    _function_coverage: DefaultDict[FunctionDefinition, int]
    _modifier_coverage: DefaultDict[ModifierDefinition, int]
    _visited_functions: Set[FunctionDefinition]
    _visited_modifiers: Set[ModifierDefinition]
    _last_statements: DefaultDict[
        Union[FunctionDefinition, ModifierDefinition],
        Optional[Tuple[Union[StatementAbc, YulStatementAbc], int]],
    ]
    _callback: Optional[Callable]

    def __init__(self, config: WakeConfig):
        compiler = SolidityCompiler(config)
        compiler.load(console=console)

        if compiler.latest_build is None or compiler.latest_build_info is None:
            raise RuntimeError(
                "Failed to load previous build. Run `wake compile` first."
            )

        self._interval_trees = dict(compiler.latest_build.interval_trees)
        self._lines_index = {}
        self._statement_coverage = defaultdict(int)
        self._function_coverage = defaultdict(int)
        self._modifier_coverage = defaultdict(int)
        self._visited_functions = set()
        self._visited_modifiers = set()
        self._last_statements = defaultdict(returning_none)
        self._callback = None

        errored = False
        for cu in compiler.latest_build_info.compilation_units.values():
            if any(e for e in cu.errors if e.severity == "error"):
                errored = True
                break

        if errored:
            console.print(
                "[yellow]Warning: There are errors in your contracts. Coverage may be inaccurate.[/yellow]"
            )

        start = time.perf_counter()
        with console.status("[bold green]Preparing coverage data...[/]"):
            self._pc_maps = _construct_coverage_data(
                compiler.latest_build, use_deployed_bytecode=True
            )
            self._pc_maps_undeployed = _construct_coverage_data(
                compiler.latest_build, use_deployed_bytecode=False
            )
            for source_unit in compiler.latest_build.source_units.values():
                self._lines_index[source_unit.file] = _setup_line_indexes(
                    source_unit.file_source
                )

        end = time.perf_counter()
        console.log(
            f"[green]Prepared coverage data in [bold green]{end - start:.2f} s[/bold green][/]"
        )

    def set_callback(self, callback: Callable) -> None:
        self._callback = callback

    def add_coverage(
        self, params: TxParams, chain: Chain, debug_trace: Dict[str, Any]
    ) -> None:
        fqn_overrides: ChainMap[Address, Optional[str]] = ChainMap()
        # TODO process fqn overrides for tx: process txs in the same block before the given tx
        # TODO what to do with call?

        if "to" not in params or params["to"] is None:
            assert "data" in params
            bytecode = params["data"]
            try:
                contract_fqn, _ = get_fqn_from_creation_code(bytecode)
                logger.info(f"Contract {contract_fqn} was deployed")
            except ValueError:
                logger.warning(f"Failed to get contract FQN for {bytecode}")
                contract_fqn = None

            self.process_trace(
                contract_fqn, debug_trace, chain, fqn_overrides, is_from_deployment=True
            )
        else:
            to = Address(params["to"])
            if to in fqn_overrides:
                contract_fqn = fqn_overrides[to]
            else:
                contract_fqn = get_fqn_from_address(
                    Address(params["to"]), "latest", chain
                )
            if contract_fqn is None:
                logger.warning(f"Failed to get contract FQN for {params['to']}")

            self.process_trace(
                contract_fqn,
                debug_trace,
                chain,
                fqn_overrides,
                is_from_deployment=False,
            )

        if self._callback is not None:
            self._callback()

    def get_contract_ide_coverage(
        self,
    ) -> Dict[pathlib.Path, Dict[IdePosition, IdeFunctionCoverageRecord]]:
        """
        Returns coverage data for IDE usage
        """
        cov_data = {}
        for func, func_count in chain(
            self._function_coverage.items(), self._modifier_coverage.items()
        ):
            if func.source_unit.file not in cov_data:
                cov_data[func.source_unit.file] = {}

            func_ide_pos = IdePosition(
                *_get_line_col_from_offset(
                    func.name_location[0], self._lines_index[func.source_unit.file]
                ),
                *_get_line_col_from_offset(
                    func.name_location[1], self._lines_index[func.source_unit.file]
                ),
            )

            branch_records = {}

            for statement, count in self._statement_coverage.items():
                if statement.source_unit.file != func.source_unit.file:
                    continue
                if isinstance(
                    statement,
                    (DoWhileStatement, ForStatement, IfStatement, WhileStatement),
                ):
                    if statement.condition is None:
                        continue
                    start, end = statement.condition.byte_location
                elif isinstance(statement, TryStatement):
                    start, end = statement.external_call.byte_location
                elif isinstance(statement, (YulForLoop, YulIf)):
                    start, end = statement.condition.byte_location
                elif isinstance(statement, YulSwitch):
                    start, end = statement.expression.byte_location
                else:
                    start, end = statement.byte_location

                if start >= func.byte_location[0] and end <= func.byte_location[1]:
                    ide_pos = IdePosition(
                        *_get_line_col_from_offset(
                            start, self._lines_index[func.source_unit.file]
                        ),
                        *_get_line_col_from_offset(
                            end, self._lines_index[func.source_unit.file]
                        ),
                    )
                    branch_records[ide_pos] = IdeCoverageRecord(ide_pos, count)

            cov_data[func.source_unit.file][func_ide_pos] = IdeFunctionCoverageRecord(
                name=func.name,
                ide_pos=func_ide_pos,
                coverage_hits=func_count,
                mod_records={},
                branch_records=branch_records,
            )

        return cov_data

    def process_trace(
        self,
        contract_fqn: Optional[str],
        trace: Dict[str, Any],
        chain: Chain,
        fqn_overrides: ChainMap[Address, Optional[str]],
        is_from_deployment: bool = False,
    ):
        """
        Processes debug_traceTransaction and it's struct_logs
        """
        contract_fqn_stack = [contract_fqn]
        is_deployment_stack = [is_from_deployment]
        assert len(fqn_overrides.maps) == 1

        for i, struct_log in enumerate(trace["structLogs"]):
            last_fqn = contract_fqn_stack[-1]
            deployment = is_deployment_stack[-1]
            pc = int(struct_log["pc"])

            if i > 0:
                prev_log = trace["structLogs"][i - 1]
                if (
                    prev_log["op"] in ("CALL", "CALLCODE", "DELEGATECALL", "STATICCALL")
                    and prev_log["depth"] == struct_log["depth"]
                ):
                    # precompiled contract was called in the previous trace
                    fqn_overrides.maps[1].update(fqn_overrides.maps[0])
                    fqn_overrides.maps.pop(0)
                    contract_fqn_stack.pop()
                    is_deployment_stack.pop()

            if struct_log["op"] in ("CALL", "CALLCODE", "DELEGATECALL", "STATICCALL"):
                logger.debug(f"Call {pc} {struct_log['op']} {struct_log['stack']}")
                addr = Address(int(struct_log["stack"][-2], 16))
                if addr in fqn_overrides:
                    new_fqn = fqn_overrides[addr]
                else:
                    new_fqn = get_fqn_from_address(addr, "latest", chain)
                contract_fqn_stack.append(new_fqn)
                is_deployment_stack.append(False)
                fqn_overrides.maps.insert(0, {})
            elif struct_log["op"] in ("CREATE", "CREATE2"):
                logger.debug(
                    f"Create call {pc} {struct_log['op']} {struct_log['memory']}"
                )
                offset = int(struct_log["stack"][-2], 16)
                length = int(struct_log["stack"][-3], 16)
                creation_code = read_from_memory(offset, length, struct_log["memory"])

                try:
                    new_fqn, _ = get_fqn_from_creation_code(creation_code)
                except ValueError:
                    logger.warning(f"Failed to get contract FQN for {creation_code}")
                    new_fqn = None

                contract_fqn_stack.append(new_fqn)
                is_deployment_stack.append(True)
                fqn_overrides.maps.insert(0, {})
            elif struct_log["op"] in {
                "INVALID",
                "RETURN",
                "STOP",
                "REVERT",
                "SELFDESTRUCT",
            }:
                logger.debug(f"{pc} {struct_log['op']} before pop {contract_fqn_stack}")
                if (
                    struct_log["op"] not in {"INVALID", "REVERT"}
                    and len(fqn_overrides.maps) > 1
                ):
                    fqn_overrides.maps[1].update(fqn_overrides.maps[0])
                fqn_overrides.maps.pop(0)

                if is_deployment_stack.pop():
                    try:
                        addr = Address(int(trace["structLogs"][i + 1]["stack"][-1], 16))
                        if addr != Address(0):
                            fqn_overrides.maps[0][addr] = contract_fqn_stack[-1]
                    except IndexError:
                        pass

                contract_fqn_stack.pop()

            pc_maps = self._pc_maps if not deployment else self._pc_maps_undeployed
            if last_fqn not in pc_maps:
                continue
            pc_map = pc_maps[last_fqn]

            if pc in pc_map:
                path = pc_map[pc].source_file
                if path is not None and path in self._interval_trees:
                    self._update_coverage(pc, pc_map[pc].offset, path)

        self._flush_coverage()

    def _update_coverage(
        self, pc: int, byte_offsets: Tuple[int, int], path: pathlib.Path
    ) -> None:
        interval_tree = self._interval_trees[path]
        start, end = byte_offsets
        intervals = interval_tree[start:end]
        nodes: List[IrAbc] = [interval.data for interval in intervals]

        functions = []
        modifiers = []
        statements = []
        yul_statements = []
        for node in nodes:
            if isinstance(node, FunctionDefinition):
                functions.append(node)
            elif isinstance(node, ModifierDefinition):
                modifiers.append(node)
            elif isinstance(node, StatementAbc):
                statements.append(node)
            elif isinstance(node, YulStatementAbc):
                yul_statements.append(node)

        function = None
        if len(functions) == 1:
            function = functions[0]
            if start >= function.byte_location[0] and end <= function.byte_location[1]:
                self._visited_functions.add(function)

        modifier = None
        if len(modifiers) == 1:
            modifier = modifiers[0]
            if start >= modifier.byte_location[0] and end <= modifier.byte_location[1]:
                self._visited_modifiers.add(modifier)

        if function is None and modifier is None:
            return
        decl = function if function is not None else modifier
        assert isinstance(decl, (FunctionDefinition, ModifierDefinition))

        if len(yul_statements) > 0:
            yul_statements.sort(key=lambda x: x.ast_tree_depth)
            yul_statement = yul_statements[-1]
            if isinstance(yul_statement, (YulBlock, YulFunctionDefinition)):
                return
            last_statement = self._last_statements[decl]
            if (
                last_statement is None
                or last_statement[0] != yul_statement
                or last_statement[1] >= pc
            ):
                if (
                    start >= yul_statement.byte_location[0]
                    and end <= yul_statement.byte_location[1]
                ):
                    self._statement_coverage[yul_statement] += 1
                    self._last_statements[decl] = (yul_statement, pc)
        elif len(statements) > 0:
            statements.sort(key=lambda x: x.ast_tree_depth)
            statement = statements[-1]
            if isinstance(statement, (Block, UncheckedBlock)):
                return
            last_statement = self._last_statements[decl]
            if (
                last_statement is None
                or last_statement[0] != statement
                or last_statement[1] >= pc
            ):
                if (
                    start >= statement.byte_location[0]
                    and end <= statement.byte_location[1]
                ):
                    self._statement_coverage[statement] += 1
                    self._last_statements[decl] = (statement, pc)

    def _flush_coverage(self) -> None:
        for fn in self._visited_functions:
            self._function_coverage[fn] += 1
        for mod in self._visited_modifiers:
            self._modifier_coverage[mod] += 1
        self._visited_functions.clear()
        self._visited_modifiers.clear()
        self._last_statements.clear()
