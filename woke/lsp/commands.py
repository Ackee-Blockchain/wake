import logging
from collections import deque
from typing import Deque, Optional, Set, Tuple

import graphviz as gv

from woke.ast.ir.declaration.contract_definition import ContractDefinition
from woke.ast.ir.declaration.function_definition import FunctionDefinition
from woke.ast.ir.declaration.modifier_definition import ModifierDefinition
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
    for declaration in source_unit.declarations_iter():
        if declaration.canonical_name == canonical_name:
            if not isinstance(declaration, (FunctionDefinition, ModifierDefinition)):
                raise LspError(
                    ErrorCodes.InvalidParams,
                    "Declaration is not a function or modifier",
                )
            cfg = declaration.cfg
            if cfg is None:
                raise LspError(
                    ErrorCodes.InternalError, "Control flow graph not available"
                )
            return cfg.to_dot()

    raise LspError(ErrorCodes.InvalidParams, "Declaration not found")


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
    g.attr("node", shape="box")

    while len(queue) > 0:
        contract, visit_base, visit_child = queue.popleft()
        node_id = f"{contract.parent.source_unit_name}_{contract.canonical_name}"
        if (
            path is not None
            and contract_info is not None
            and contract.file == path
            and contract.canonical_name == contract_info[1]
        ):
            g.node(node_id, contract.canonical_name, style="filled")
        else:
            g.node(node_id, label=contract.canonical_name)

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
