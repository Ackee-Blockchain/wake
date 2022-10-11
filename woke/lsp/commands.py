import logging
from collections import deque
from typing import Deque, List, Optional, Set, Tuple

import graphviz as gv

from woke.ast.ir.declaration.contract_definition import ContractDefinition
from woke.ast.ir.declaration.function_definition import FunctionDefinition
from woke.ast.ir.declaration.modifier_definition import ModifierDefinition
from woke.ast.ir.statement.abc import StatementAbc
from woke.lsp.common_structures import DocumentUri
from woke.lsp.context import LspContext
from woke.lsp.exceptions import LspError
from woke.lsp.protocol_structures import ErrorCodes
from woke.lsp.utils import uri_to_path

logger = logging.getLogger(__name__)


async def generate_cfg_handler(
    context: LspContext, uri: DocumentUri, canonical_name: str
) -> str:
    logger.debug(
        f"Control flow graph for function {canonical_name} in file {uri} requested"
    )
    await context.compiler.output_ready.wait()

    path = uri_to_path(uri).resolve()

    if path not in context.compiler.source_units:
        raise LspError(ErrorCodes.InternalError, "File not found in compiler output")

    source_unit = context.compiler.source_units[path]
    target_declaration = None
    for declaration in source_unit.declarations_iter():
        if declaration.canonical_name == canonical_name:
            if not isinstance(declaration, (FunctionDefinition, ModifierDefinition)):
                raise LspError(
                    ErrorCodes.InvalidParams,
                    "Declaration is not a function or modifier",
                )
            target_declaration = declaration
            break

    if target_declaration is None:
        raise LspError(ErrorCodes.InvalidParams, "Declaration not found")

    cfg = target_declaration.cfg
    if cfg is None:
        raise LspError(ErrorCodes.InternalError, "Control flow graph not available")
    graph = cfg.graph

    g = gv.Digraph(f"{canonical_name} control flow graph")
    g.attr(rankdir=context.config.generator.control_flow_graph.direction)
    g.attr("node", shape="box")

    for node in graph.nodes:
        statements: List[StatementAbc] = node.statements
        node_attrs = {"label": str(node)}
        if (
            context.config.generator.control_flow_graph.vscode_urls
            and len(statements) > 0
        ):
            first_statement = statements[0]
            line, column = context.compiler.get_line_pos_from_byte_offset(
                first_statement.file, first_statement.byte_location[0]
            )
            line += 1
            column += 1
            node_attrs["URL"] = f"vscode://file/{first_statement.file}:{line}:{column}"
        g.node(str(node.id), **node_attrs)

    for from_, to, data in graph.edges.data():
        condition = data["condition"]
        if condition[1] is not None:
            label = f"{condition[1].source} {condition[0]}"
        else:
            label = condition[0]
        g.edge(str(from_.id), str(to.id), label=label)

    return g.source


async def generate_inheritance_graph_handler(
    context: LspContext, contract_info: Optional[Tuple[DocumentUri, str]]
) -> str:
    await context.compiler.output_ready.wait()

    queue: Deque[Tuple[ContractDefinition, bool, bool]] = deque()
    visited: Set[ContractDefinition] = set()

    if contract_info is not None:
        path = uri_to_path(contract_info[0]).resolve()

        if path not in context.compiler.source_units:
            raise LspError(
                ErrorCodes.InternalError, "File not found in compiler output"
            )

        source_unit = context.compiler.source_units[path]
        found = False
        for contract in source_unit.contracts:
            if contract.canonical_name == contract_info[1]:
                queue.append((contract, True, True))
                visited.add(contract)
                found = True
                break
        if not found:
            raise LspError(ErrorCodes.InvalidParams, "Contract not found")
    else:
        path = None
        for source_unit in context.compiler.source_units.values():
            for contract in source_unit.contracts:
                if len(contract.base_contracts) == 0:
                    queue.append((contract, False, True))
                    visited.add(contract)

    if len(queue) == 0:
        raise LspError(ErrorCodes.InternalError, "No contracts found")

    g = gv.Digraph(
        f"{contract_info[1]} inheritance graph"
        if contract_info is not None
        else "Inheritance graph"
    )
    g.attr(rankdir=context.config.generator.inheritance_graph.direction)
    g.attr("node", shape="box")

    while len(queue) > 0:
        contract, visit_base, visit_child = queue.popleft()
        node_id = f"{contract.parent.source_unit_name}_{contract.canonical_name}"
        node_attrs = {}
        if (
            path is not None
            and contract_info is not None
            and contract.file == path
            and contract.canonical_name == contract_info[1]
        ):
            node_attrs["style"] = "filled"

        if context.config.generator.inheritance_graph.vscode_urls:
            line, column = context.compiler.get_line_pos_from_byte_offset(
                contract.file, contract.name_location[0]
            )
            line += 1
            column += 1
            node_attrs["URL"] = f"vscode://file/{contract.file}:{line}:{column}"

        g.node(node_id, contract.canonical_name, **node_attrs)

        if visit_base:
            for parent in contract.base_contracts:
                parent_contract = parent.base_name.referenced_declaration
                assert isinstance(parent_contract, ContractDefinition)
                g.edge(
                    node_id,
                    f"{parent_contract.parent.source_unit_name}_{parent_contract.canonical_name}",
                )
                if parent_contract not in visited:
                    visited.add(parent_contract)
                    queue.append((parent_contract, True, False))

        if visit_child:
            for child_contract in contract.child_contracts:
                g.edge(
                    f"{child_contract.parent.source_unit_name}_{child_contract.canonical_name}",
                    node_id,
                )
                if child_contract not in visited:
                    visited.add(child_contract)
                    queue.append((child_contract, False, True))

    return g.source


async def generate_linearized_inheritance_graph_handler(
    context: LspContext, uri: DocumentUri, canonical_name: str
) -> str:
    logger.debug(
        f"Linearized inheritance graph for contract {canonical_name} in file {uri} requested"
    )
    await context.compiler.output_ready.wait()

    path = uri_to_path(uri).resolve()

    if path not in context.compiler.source_units:
        raise LspError(ErrorCodes.InternalError, "File not found in compiler output")

    source_unit = context.compiler.source_units[path]
    target_contract = None
    for contract in source_unit.contracts:
        if contract.canonical_name == canonical_name:
            target_contract = contract
            break

    if target_contract is None:
        raise LspError(ErrorCodes.InvalidParams, "Contract not found")

    g = gv.Digraph(f"{canonical_name} linearized inheritance graph")
    g.attr(rankdir=context.config.generator.linearized_inheritance_graph.direction)
    g.attr("node", shape="box")

    prev_node_id = None

    for contract in target_contract.linearized_base_contracts:
        node_id = f"{contract.parent.source_unit_name}_{contract.canonical_name}"
        node_attrs = {}
        if contract.file == path and contract.canonical_name == canonical_name:
            node_attrs["style"] = "filled"

        if context.config.generator.linearized_inheritance_graph.vscode_urls:
            line, column = context.compiler.get_line_pos_from_byte_offset(
                contract.file, contract.name_location[0]
            )
            line += 1
            column += 1
            node_attrs["URL"] = f"vscode://file/{contract.file}:{line}:{column}"

        g.node(node_id, contract.canonical_name, **node_attrs)
        if prev_node_id is not None:
            g.edge(prev_node_id, node_id)
        prev_node_id = node_id
    return g.source
