import logging
from typing import List

import graphviz as gv

from wake.core import get_logger
from wake.ir import FunctionDefinition, ModifierDefinition, StatementAbc
from wake.lsp.common_structures import DocumentUri
from wake.lsp.context import LspContext
from wake.lsp.exceptions import LspError
from wake.lsp.protocol_structures import ErrorCodes
from wake.lsp.utils import uri_to_path

logger = get_logger(__name__)


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

    if not target_declaration.implemented:
        raise LspError(ErrorCodes.InternalError, "Control flow graph not available")

    cfg = target_declaration.cfg
    graph = cfg.graph

    g = gv.Digraph(f"{canonical_name} control flow graph")
    g.attr(rankdir=context.config.generator.control_flow_graph.direction)
    g.attr("node", shape="box")

    skip_start_node = False
    if (
        len(cfg.start_node.statements) == 0
        and cfg.start_node.control_statement is None
        and graph.out_degree(cfg.start_node)  # pyright: ignore reportGeneralTypeIssues
        == 1
    ):
        skip_start_node = True

    for node in graph.nodes:  # pyright: ignore reportGeneralTypeIssues
        if skip_start_node and node == cfg.start_node:
            continue

        statements: List[StatementAbc] = node.statements
        node_attrs = {
            "label": "".join(
                f"{line}\l"  # pyright: ignore reportInvalidStringEscapeSequence
                for line in str(node).splitlines()
            )
        }

        if node == cfg.success_end_node:
            node_attrs["color"] = "green"
            node_attrs["xlabel"] = "success"
        elif node == cfg.revert_end_node:
            node_attrs["color"] = "red"
            node_attrs["xlabel"] = "revert"

        if (
            context.config.generator.control_flow_graph.vscode_urls
            and len(statements) > 0
        ):
            first_statement = statements[0]
            line, column = context.compiler.get_line_pos_from_byte_offset(
                first_statement.source_unit.file, first_statement.byte_location[0]
            )
            line += 1
            column += 1
            node_attrs[
                "URL"
            ] = f"vscode://file/{first_statement.source_unit.file}:{line}:{column}"
        g.node(str(node.id), **node_attrs)

    for (
        from_,
        to,
        data,
    ) in graph.edges.data():  # pyright: ignore reportGeneralTypeIssues
        if skip_start_node and from_ == cfg.start_node:
            continue

        condition = data["condition"]  # pyright: ignore reportOptionalSubscript
        if condition[1] is not None:
            label = f"{condition[1].source} {condition[0]}"
        else:
            label = condition[0]
        g.edge(str(from_.id), str(to.id), label=label)

    return g.source
