import logging
from collections import deque
from typing import Deque, Optional, Set, Tuple

import graphviz as gv

from wake.core import get_logger
from wake.ir import ContractDefinition
from wake.lsp.common_structures import DocumentUri
from wake.lsp.context import LspContext
from wake.lsp.exceptions import LspError
from wake.lsp.protocol_structures import ErrorCodes
from wake.lsp.utils import uri_to_path

logger = get_logger(__name__)


async def generate_inheritance_graph_handler(
    context: LspContext, contract_info: Optional[Tuple[DocumentUri, str]]
) -> str:
    if contract_info is None:
        logger.debug(f"Requested inheritance graph for all contracts")
    else:
        logger.debug(
            f"Inheritance graph for contract {contract_info[1]} in file {contract_info[0]} requested"
        )
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

    if contract_info is None:
        config = context.config.generator.inheritance_graph_full
    else:
        config = context.config.generator.inheritance_graph

    g = gv.Digraph(
        f"{contract_info[1]} inheritance graph"
        if contract_info is not None
        else "Inheritance graph"
    )
    g.attr(rankdir=config.direction)
    g.attr("node", shape="box")

    while len(queue) > 0:
        contract, visit_base, visit_child = queue.popleft()
        node_id = f"{contract.parent.source_unit_name}_{contract.canonical_name}"
        node_attrs = {}
        if (
            path is not None
            and contract_info is not None
            and contract.source_unit.file == path
            and contract.canonical_name == contract_info[1]
        ):
            node_attrs["style"] = "filled"

        if config.vscode_urls:
            line, column = context.compiler.get_line_pos_from_byte_offset(
                contract.source_unit.file, contract.name_location[0]
            )
            line += 1
            column += 1
            node_attrs[
                "URL"
            ] = f"vscode://file/{contract.source_unit.file}:{line}:{column}"

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
