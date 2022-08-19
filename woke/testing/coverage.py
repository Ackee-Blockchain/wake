import asyncio
import logging
import pathlib
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

import intervaltree
from intervaltree import IntervalTree

import woke.compile
import woke.config
from woke.ast.ir.declaration.function_definition import FunctionDefinition
from woke.ast.ir.declaration.modifier_definition import ModifierDefinition
from woke.ast.ir.meta.source_unit import SourceUnit
from woke.ast.ir.reference_resolver import CallbackParams, ReferenceResolver
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import AstSolc
from woke.compile import SolcOutput
from woke.compile.compilation_unit import CompilationUnit
from woke.compile.solc_frontend import (
    SolcOutputErrorSeverityEnum,
    SolcOutputSelectionEnum,
)
from woke.testing import default_chain
from woke.testing.core import Address, get_fqn_from_address, get_fqn_from_bytecode
from woke.testing.development_chains import DevChainABC
from woke.utils.file_utils import is_relative_to

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


BRANCH_INSTRUCTIONS = [
    "JUMPI",
    "JUMPDEST",
    "CALL",
    "CALLCODE",
    "DELEGATECALL",
    "STATICCALL",
    "REVERT",
]


@dataclass
class BytecodeInfo:
    opcodes: str
    source_map: str


@dataclass
class SourceMapRecord:
    fn: str
    offset: Tuple[int, int]
    jump_type: str
    op: str


class ContractCoverage:
    pc_map: Dict[int, SourceMapRecord]
    all_instr: Dict[int, int]
    branch_instr: Dict[int, int]
    function_instr: Dict[str, Set[int]]

    def __init__(self, pc_map):
        self.pc_map = pc_map
        self.all_instr = {}
        self.branch_instr = {}
        self.function_instr = {}

        self._add_branch_coverage()
        self._add_instruction_coverage()

    def add_cov(self, pc: int):
        if pc in self.all_instr:
            self.all_instr[pc] += 1
        if pc in self.branch_instr:
            self.branch_instr[pc] += 1

    def _get_function_coverage(
        self, pc_dict: Dict[int, int]
    ) -> Dict[str, Tuple[int, int]]:
        fn_pcs = {}

        for fn, pc_set in self.function_instr.items():
            pc_set_pc_dict = [pc for pc in pc_set if pc in pc_dict]
            fn_pcs[fn] = (
                sum([1 for pc in pc_set_pc_dict if pc_dict[pc] != 0]),
                len(pc_set_pc_dict),
            )

        return fn_pcs

    def get_function_instr_coverage(self) -> Dict[str, Tuple[int, int]]:
        """
        Returns (x,y) where x is number of executed instructions and y is number of all
        instructions for a function
        """
        return self._get_function_coverage(self.all_instr)

    def get_function_branch_coverage(self) -> Dict[str, Tuple[int, int]]:  # TODO
        return self._get_function_coverage(self.branch_instr)

    def get_source_instr_coverage(self) -> Dict[Tuple[int, int], int]:
        """
        Returns maximum number of instruction executions from coverage for offsets
        in contract file
        """
        source_cov = {}

        for pc, rec in self.pc_map.items():
            if pc in self.all_instr and (
                rec.offset not in source_cov
                or self.all_instr[pc] > source_cov[rec.offset]
            ):
                source_cov[rec.offset] = self.all_instr[pc]

        return source_cov

    def _add_branch_coverage(self):
        first_pcs = [(pc, rec.fn, rec.offset) for pc, rec in self.pc_map.items()]
        first_pcs.sort(key=lambda t: t[2][0])
        first_pcs_fn = set()

        for pc, fn, _ in first_pcs:
            if fn not in first_pcs_fn:
                first_pcs_fn.add(fn)
                self.branch_instr[pc] = 0
                if fn not in self.function_instr:
                    self.function_instr[fn] = set()
                self.function_instr[fn].add(pc)

        for pc, rec in self.pc_map.items():
            if rec.fn not in self.function_instr:
                self.function_instr[rec.fn] = set()
            if rec.op in BRANCH_INSTRUCTIONS:
                if rec.jump_type is not None and rec.jump_type == "o":
                    continue
                self.function_instr[rec.fn].add(pc)
                self.branch_instr[pc] = 0

    def _add_instruction_coverage(self):
        for pc, rec in self.pc_map.items():
            if rec.fn not in self.function_instr:
                self.function_instr[rec.fn] = set()
            self.function_instr[rec.fn].add(pc)
            self.all_instr[pc] = 0


def _parse_opcodes(opcodes: str) -> List[Tuple[int, str]]:
    pc_op_map = []
    opcodes_spl = opcodes.split(" ")

    pc = 0
    ignore = False

    for opcode in opcodes_spl:
        if ignore:
            ignore = False
            continue
        pc_op_map.append((pc, opcode))
        # logger.debug(f"opcode {pc} opcode {opcode}")
        pc += 1

        if not opcode.startswith("PUSH"):
            continue

        pc += int(opcode[4:])
        ignore = True
    return pc_op_map


def _find_fn_for_source(
    interval_tree: intervaltree.IntervalTree, source_from: int, source_to: int
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
) -> Tuple[Dict[pathlib.Path, SourceUnit], Dict[pathlib.Path, IntervalTree],]:
    processed_files: Set[pathlib.Path] = set()
    reference_resolver = ReferenceResolver()
    interval_trees: Dict[pathlib.Path, IntervalTree] = {}
    source_units: Dict[pathlib.Path, SourceUnit] = {}

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

    reference_resolver.run_post_process_callbacks(
        CallbackParams(interval_trees=interval_trees, source_units=source_units)
    )
    return source_units, interval_trees


def _compile_project() -> List[Tuple[CompilationUnit, SolcOutput]]:
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
    interval_tree: IntervalTree, source_map: str, pc_op_pairs: List[Tuple[int, str]]
) -> Dict[int, SourceMapRecord]:
    pc_map = {}
    source_map_spl = source_map.split(";")

    last_data = [-1, -1, -1, None, None]
    last_fn = None
    fn_changed = False
    name_cache = {}

    for i in range(len(source_map_spl)):
        pc, op = pc_op_pairs[i]
        source_spl = source_map_spl[i].split(":")
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
            pc_map[pc] = SourceMapRecord(last_fn, source_interval, last_data[3], op)

    return pc_map


def _construct_coverage_data() -> Dict[str, ContractCoverage]:
    outputs = _compile_project()
    source_units, interval_trees = _parse_project(outputs)
    contracts_cov = {}

    for unit_path, source_unit in source_units.items():
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

            pc_op_map = _parse_opcodes(opcodes)
            pc_map = _parse_source_map(interval_trees[unit_path], source_map, pc_op_map)

            contract_fqn = f"{source_unit.source_unit_name}:{contract.name}"
            contracts_cov[contract_fqn] = ContractCoverage(pc_map)
    return contracts_cov


class Coverage:
    _dev_chain: DevChainABC
    _contracts_cov: Dict[str, ContractCoverage]
    _last_covered_block: int

    def __init__(
        self,
        starter_block: Optional[int] = None,
    ):
        self._dev_chain = default_chain.dev_chain
        self._contracts_cov = _construct_coverage_data()
        self._last_covered_block = starter_block if starter_block is not None else 0

    def get_covered_contracts(self):
        """
        Returns covered contract names that can be then used in other methods
        """
        return self._contracts_cov.keys()

    def get_contract_coverage(self, contract_fqn: str) -> ContractCoverage:
        """
        Returns ContractCoverage for given contract name
        """
        return self._contracts_cov[contract_fqn]

    def get_coverage(self) -> Dict[str, ContractCoverage]:
        """
        Returns all contracts coverage
        """
        return self._contracts_cov

    def process_trace(self, contract_fqn: str, trace: Dict["str", Any]):
        """
        Processes debug_traceTransaction and it's struct_logs
        """
        for struct_log in trace["structLogs"]:
            pc = int(struct_log["pc"])
            logger.debug(f"{pc} {struct_log['op']} is is called")
            self._contracts_cov[contract_fqn].add_cov(pc)

    def update_coverage(self):
        """
        Checks for latest transactions on blockchain for
        """
        last_block = self._dev_chain.get_block_number()
        if (
            self._last_covered_block > last_block
        ):  # chain was reset -> reset last_covered_block
            self._last_covered_block = 0

        for block_number in range(self._last_covered_block, last_block):
            block_info = self._dev_chain.get_block(block_number, True)
            for transaction in block_info["transactions"]:
                if "to" not in transaction:
                    assert "data" in transaction
                    bytecode = transaction["data"]
                    if bytecode.startswith("0x"):
                        bytecode = bytecode[2:]
                    bytecode = bytes.fromhex(bytecode)
                    contract_fqn = get_fqn_from_bytecode(bytecode)
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
                        "disableStack": True,
                        "disableStorage": True,
                    },
                )
                self.process_trace(contract_fqn, trace)
        self._last_covered_block = last_block
