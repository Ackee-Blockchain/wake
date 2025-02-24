import time
from typing import Dict, List, Optional, Tuple

from wake.cli.console import console
from wake.compiler.build_data_model import ProjectBuild
from wake.compiler.compiler import SolidityCompiler
from wake.config.wake_config import WakeConfig
from wake.ir import (
    Block,
    DoWhileStatement,
    ForStatement,
    IfStatement,
    InlineAssembly,
    TryStatement,
    UncheckedBlock,
    WhileStatement,
    YulBlock,
    YulForLoop,
    YulFunctionDefinition,
    YulIf,
    YulSwitch,
)

collect_coverage: bool = False
sync_timeout: float

pc_map: Dict[str, Dict[int, Tuple[str, int, int]]]
deployment_pc_map: Dict[str, Dict[int, Tuple[str, int, int]]]
flattened_ast: Dict[str, List[Tuple[str, int, int, int, str]]]


def _setup_flattened_ast(build: ProjectBuild):
    flattened_ast = {}

    for source_unit in build.source_units.values():
        list_of_nodes: List[Tuple[str, int, int, int, str]] = []
        for node in source_unit:
            if isinstance(
                node, (DoWhileStatement, ForStatement, IfStatement, WhileStatement)
            ):
                if node.condition is not None:
                    list_of_nodes.append(
                        (
                            node.ast_node.node_type,
                            node.condition.byte_location[0],
                            node.condition.byte_location[1],
                            node.ast_tree_depth,
                            node.condition.source,
                        )
                    )
            elif isinstance(node, TryStatement):
                list_of_nodes.append(
                    (
                        node.ast_node.node_type,
                        node.external_call.byte_location[0],
                        node.external_call.byte_location[1],
                        node.ast_tree_depth,
                        node.external_call.source,
                    )
                )
            elif isinstance(node, (YulForLoop, YulIf)):
                list_of_nodes.append(
                    (
                        node.ast_node.node_type,
                        node.condition.byte_location[0],
                        node.condition.byte_location[1],
                        node.ast_tree_depth,
                        node.condition.source,
                    )
                )
            elif isinstance(node, YulSwitch):
                list_of_nodes.append(
                    (
                        node.ast_node.node_type,
                        node.expression.byte_location[0],
                        node.expression.byte_location[1],
                        node.ast_tree_depth,
                        node.expression.source,
                    )
                )
            elif isinstance(
                node,
                (
                    Block,
                    UncheckedBlock,
                    InlineAssembly,
                    YulBlock,
                    YulFunctionDefinition,
                ),
            ):
                pass
            else:
                list_of_nodes.append(
                    (
                        node.ast_node.node_type,
                        node.byte_location[0],
                        node.byte_location[1],
                        node.ast_tree_depth,
                        node.source,
                    )
                )

        flattened_ast[source_unit.source_unit_name] = list_of_nodes

    return flattened_ast


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
    build: ProjectBuild,
    source_map: str,
    pc_op_map: List[Tuple[int, str, int, Optional[int]]],
) -> Dict[int, Tuple[int, int, int]]:
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

        try:
            path = build.reference_resolver.resolve_source_file_id(
                last_data[2], cu_hash
            )
            source_unit_name = build.source_units[path].source_unit_name
        except KeyError:
            continue

        pc_map[pc] = (source_unit_name, last_data[0], last_data[0] + last_data[1])

    return pc_map


def _setup_pc_map(
    build: ProjectBuild, use_deployed_bytecode: bool = True
) -> Dict[str, Dict[int, Tuple[str, int, int]]]:
    pc_map = {}

    for source_unit in build.source_units.values():
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

            pc_op_map = _parse_opcodes(opcodes)
            pc_map[
                f"{source_unit.source_unit_name}:{contract.name}"
            ] = _parse_source_map(source_unit.cu_hash, build, source_map, pc_op_map)

    return pc_map


class NativeCoverageHandler:
    latest_build: ProjectBuild
    sync_timeout: float
    pc_map: Dict[str, Dict[int, Tuple[str, int, int]]]
    deployment_pc_map: Dict[str, Dict[int, Tuple[str, int, int]]]
    flattened_ast: Dict[str, List[Tuple[str, int, int, int, str]]]

    def __init__(self, config: WakeConfig):
        global collect_coverage, sync_timeout, pc_map, deployment_pc_map, flattened_ast

        self.sync_timeout = config.testing.coverage_sync_timeout

        compiler = SolidityCompiler(config)
        compiler.load(console=console)

        if compiler.latest_build is None or compiler.latest_build_info is None:
            raise RuntimeError(
                "Failed to load previous build. Run `wake compile` first."
            )

        self.latest_build = compiler.latest_build

        start = time.perf_counter()
        with console.status("[bold green]Preparing coverage data...[/]"):
            self.pc_map = _setup_pc_map(
                compiler.latest_build, use_deployed_bytecode=True
            )
            self.deployment_pc_map = _setup_pc_map(
                compiler.latest_build, use_deployed_bytecode=False
            )

            self.flattened_ast = _setup_flattened_ast(compiler.latest_build)

        end = time.perf_counter()
        console.log(
            f"[green]Prepared coverage data in [bold green]{end - start:.2f} s[/bold green][/]"
        )

        collect_coverage = True
        sync_timeout = self.sync_timeout
        pc_map = self.pc_map
        deployment_pc_map = self.deployment_pc_map
        flattened_ast = self.flattened_ast

    def __setstate__(self, state):
        global collect_coverage, sync_timeout, pc_map, deployment_pc_map, flattened_ast

        self.__dict__.update(state)
        self.latest_build.fix_after_deserialization(lsp=False)

        collect_coverage = True
        sync_timeout = self.sync_timeout
        pc_map = self.pc_map
        deployment_pc_map = self.deployment_pc_map
        flattened_ast = self.flattened_ast
