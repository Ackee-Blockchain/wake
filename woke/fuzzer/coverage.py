import asyncio
import logging
import pathlib
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

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
from woke.compile.solc_frontend import SolcOutputSelectionEnum
from woke.json_rpc import communicator
from woke.json_rpc.data_model import JsonRpcTransaction, JsonRpcTransactionTrace

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

            interval_trees[path] = IntervalTree()
            ast = AstSolc.parse_obj(info.ast)

            reference_resolver.index_nodes(ast, path, cu.hash)

            if path in processed_files:
                continue
            processed_files.add(path)

            init = IrInitTuple(
                path,
                path.read_bytes(),
                cu,
                interval_trees[path],
                reference_resolver,
            )
            source_units[path] = SourceUnit(init, ast)

    reference_resolver.run_post_process_callbacks(
        CallbackParams(source_units=source_units)
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
    source_units, interval_trees, bytecode_infos = _parse_project(outputs)
    contracts_cov = {}
    for unit_path, unit in source_units.items():
        for contract in unit.contracts:
            if (
                unit_path not in bytecode_infos
                or contract.name not in bytecode_infos[unit_path]
            ):
                continue
            opcodes = bytecode_infos[unit_path][contract.name].opcodes
            source_map = bytecode_infos[unit_path][contract.name].source_map

            pc_op_map = _parse_opcodes(opcodes)
            pc_map = _parse_source_map(interval_trees[unit_path], source_map, pc_op_map)

            contracts_cov[contract.name] = ContractCoverage(pc_map)
    return contracts_cov


class Coverage:
    _comm: communicator.JsonRpcCommunicator
    _contracts_cov: Dict[str, ContractCoverage]
    _last_covered_block: int

    def __init__(
        self,
        comm: communicator.JsonRpcCommunicator,
        starter_block: Optional[int] = None,
    ):
        self._comm = comm
        self._contracts_cov = _construct_coverage_data()
        self._last_covered_block = starter_block if starter_block is not None else 0

    def get_covered_contracts(self):
        """
        Returns covered contract names that can be then used in other methods
        """
        return self._contracts_cov.keys()

    def get_contract_coverage(self, contract: str) -> ContractCoverage:
        """
        Returns ContractCoverage for given contract name
        """
        return self._contracts_cov[contract]

    async def process_trace(self, contract_name: str, trace: JsonRpcTransactionTrace):
        """
        Processes JsonRpcTransactionTrace and it's struct_logs
        """
        for struct_log in trace.struct_logs:
            pc = int(struct_log.pc)
            logger.debug(f"{pc} {struct_log.op} is is called")
            self._contracts_cov[contract_name].add_cov(pc)

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
                await self.process_trace(contract_name, trace)
        self._last_covered_block = last_block
