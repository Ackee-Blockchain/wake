import logging

import graphviz as gv

from woke.lsp.common_structures import DocumentUri
from woke.lsp.context import LspContext
from woke.lsp.exceptions import LspError
from woke.lsp.protocol_structures import ErrorCodes
from woke.lsp.utils import uri_to_path

logger = logging.getLogger(__name__)


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
