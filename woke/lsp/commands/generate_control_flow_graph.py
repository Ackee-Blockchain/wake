import logging
from typing import List

import graphviz as gv

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
