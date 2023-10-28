import logging

import graphviz as gv

from wake.config.data_model import ImportsDirection
from wake.core import get_logger
from wake.lsp.context import LspContext

logger = get_logger(__name__)


async def generate_imports_graph_handler(context: LspContext) -> str:
    logger.debug(f"Requested imports graph")

    await context.compiler.output_ready.wait()

    config = context.config.generator.imports_graph

    g = gv.Digraph("Imports graph")
    g.attr(rankdir=config.direction)
    g.attr("node", shape="box")

    graph = context.compiler.last_graph

    for node in graph.nodes:  # pyright: ignore reportGeneralTypeIssues
        node_attrs = {}
        if config.vscode_urls:
            node_attrs[
                "URL"
            ] = f"vscode://file/{graph.nodes[node]['path']}"  # pyright: ignore reportGeneralTypeIssues
        g.node(node, **node_attrs)

    for from_, to in graph.edges:  # pyright: ignore reportGeneralTypeIssues
        if config.imports_direction == ImportsDirection.ImportedToImporting:
            g.edge(from_, to)
        else:
            g.edge(to, from_)

    return g.source
