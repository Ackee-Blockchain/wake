from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Set, Tuple

import networkx as nx
import rich_click as click
from rich import print

import wake.ir as ir
import wake.ir.types as types
from wake.printers import Printer, printer


class ImportsGraphPrinter(Printer):
    _out: Path
    _graph_direction: str
    _edge_direction: str
    _links: bool
    _force: bool
    _importers: bool
    _imported: bool

    def print(self) -> None:
        import graphviz as gv

        if not self._force and self._out.exists():
            self.logger.warning(f"File {self._out} already exists, skipping")
            return

        g = gv.Digraph("Imports graph")
        g.attr(rankdir=self._graph_direction)
        g.attr("node", shape="box")

        paths = set(self.paths)

        if len(paths) == 0:
            visited = set(
                self.imports_graph.nodes  # pyright: ignore reportGeneralTypeIssues
            )
            queue = deque(
                (s, self._importers, self._imported)
                for s in self.imports_graph.nodes  # pyright: ignore reportGeneralTypeIssues
            )
        else:
            visited = set()
            queue = deque([])
            for source_unit_name, path in self.imports_graph.nodes(
                data="path"  # pyright: ignore reportGeneralTypeIssues
            ):
                if path in paths:
                    visited.add(source_unit_name)
                    queue.append((source_unit_name, self._importers, self._imported))

        edges: Set[Tuple[str, str]] = set()

        while len(queue) != 0:
            source_unit_name, visit_importers, visit_imported = queue.popleft()
            path = self.imports_graph.nodes[  # pyright: ignore reportGeneralTypeIssues
                source_unit_name
            ]["path"]
            node_attrs = {}
            if path in paths:
                node_attrs["style"] = "filled"
            if self._links and path in self.build.source_units:
                node_attrs["URL"] = self.generate_link(self.build.source_units[path])

            g.node(source_unit_name, **node_attrs)

            for pred in self.imports_graph.predecessors(source_unit_name):
                pred_path = (
                    self.imports_graph.nodes[  # pyright: ignore reportGeneralTypeIssues
                        pred
                    ]["path"]
                )
                if visit_importers or pred_path in paths:
                    if self._edge_direction == "imported-to-importing":
                        edges.add((pred, source_unit_name))
                    else:
                        edges.add((source_unit_name, pred))
                    if pred not in visited:
                        visited.add(pred)
                        queue.append((pred, True, False))

            for succ in self.imports_graph.successors(source_unit_name):
                succ_path = (
                    self.imports_graph.nodes[  # pyright: ignore reportGeneralTypeIssues
                        succ
                    ]["path"]
                )
                if visit_imported or succ_path in paths:
                    if self._edge_direction == "imported-to-importing":
                        edges.add((source_unit_name, succ))
                    else:
                        edges.add((succ, source_unit_name))
                    if succ not in visited:
                        visited.add(succ)
                        queue.append((succ, False, True))

        for from_, to in edges:
            g.edge(from_, to)

        g.save(self._out)

    @printer.command(name="imports-graph")
    @click.option(
        "-o",
        "--out",
        is_flag=False,
        default=".wake/imports-graph.dot",
        type=click.Path(file_okay=True, dir_okay=False, writable=True),
        help="Output file",
    )
    @click.option(
        "--graph-direction",
        type=click.Choice(["LR", "TB", "BT", "RL"]),
        default="TB",
        help="Graph direction",
    )
    @click.option(
        "--edge-direction",
        type=click.Choice(["imported-to-importing", "importing-to-imported"]),
        default="imported-to-importing",
        help="Edge direction",
    )
    @click.option(
        "--links/--no-links",
        default=True,
        help="Generate links to source code",
    )
    @click.option(
        "--force",
        "-f",
        is_flag=True,
        default=False,
        help="Overwrite existing files",
    )
    @click.option(
        "--importers/--no-importers",
        default=True,
        help="Generate files that import the specified files",
    )
    @click.option(
        "--imported/--no-imported",
        default=True,
        help="Generate files that are imported by the specified files",
    )
    def cli(
        self,
        out: str,
        graph_direction: str,
        edge_direction: str,
        links: bool,
        force: bool,
        importers: bool,
        imported: bool,
    ) -> None:
        """
        Generate imports graph.
        """
        self._out = Path(out).resolve()
        self._out.parent.mkdir(parents=True, exist_ok=True)
        self._graph_direction = graph_direction
        self._edge_direction = edge_direction
        self._links = links
        self._force = force
        self._importers = importers
        self._imported = imported
