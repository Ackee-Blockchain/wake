import logging

import graphviz as gv

from woke.config.data_model import ImportsDirection
from woke.lsp.context import LspContext

logger = logging.getLogger(__name__)


async def generate_imports_graph_handler(context: LspContext) -> str:
    logger.debug(f"Requested imports graph")

    await context.compiler.output_ready.wait()

    config = context.config.generator.imports_graph

    g = gv.Digraph("Imports graph")
    g.attr(rankdir=config.direction)
    g.attr("node", shape="box")

    graph = context.compiler.last_graph

    for node in graph.nodes:
        node_attrs = {}
        if config.vscode_urls:
            node_attrs["URL"] = f"vscode://file/{graph.nodes[node]['path']}"
        g.node(node, **node_attrs)

    for from_, to in graph.edges:
        if config.imports_direction == ImportsDirection.ImportedToImporting:
            g.edge(from_, to)
        else:
            g.edge(to, from_)

    return g.source
