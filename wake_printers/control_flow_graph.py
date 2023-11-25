from __future__ import annotations

from pathlib import Path
from typing import Set, Tuple, Union

import networkx as nx
import rich_click as click
from rich import print

import wake.ir as ir
import wake.ir.types as types
from wake.cli import SolidityName
from wake.printers import Printer, printer


class ControlFlowGraphPrinter(Printer):
    _names: Set[str]
    _out: Path
    _direction: str
    _links: bool
    _force: bool

    def print(self) -> None:
        pass

    def _generate(self, node: Union[ir.FunctionDefinition, ir.ModifierDefinition]):
        import graphviz as gv

        if (
            len(self._names) != 0
            and node.name not in self._names
            and node.canonical_name not in self._names
            or not node.implemented
        ):
            return

        cfg = node.cfg
        p = self._out / f"{node.canonical_name.replace('.', '_')}.dot"
        if not self._force and p.exists():
            self.logger.warning(f"File {p} already exists, skipping")
            return

        g = gv.Digraph(f"{node.canonical_name} control flow graph")
        g.attr(rankdir=self._direction)
        g.attr("node", shape="box")

        skip_start_node = (
            len(cfg.start_node.statements) == 0
            and cfg.start_node.control_statement is None
            and cfg.graph.out_degree(
                cfg.start_node  # pyright: ignore reportGeneralTypeIssues
            )
            == 1
        )

        for n in cfg.graph.nodes:  # pyright: ignore reportGeneralTypeIssues
            if skip_start_node and n == cfg.start_node:
                continue

            node_attrs = {
                "label": "".join(
                    f"{line}\l"  # pyright: ignore reportInvalidStringEscapeSequence
                    for line in str(n).splitlines()
                )
            }

            if n == cfg.success_end_node:
                node_attrs["color"] = "green"
                node_attrs["xlabel"] = "success"
            elif n == cfg.revert_end_node:
                node_attrs["color"] = "red"
                node_attrs["xlabel"] = "revert"

            if self._links and len(n.statements) > 0:
                node_attrs["URL"] = self.generate_link(n.statements[0])

            g.node(str(n.id), **node_attrs)

        for from_, to, data in cfg.graph.edges.data():
            if skip_start_node and from_ == cfg.start_node:
                continue

            condition = data["condition"]
            if condition[1] is not None:
                label = f"{condition[1].source} {condition[0]}"
            else:
                label = condition[0]

            g.edge(str(from_.id), str(to.id), label=label)

        g.save(p)

    def visit_function_definition(self, node: ir.FunctionDefinition):
        self._generate(node)

    def visit_modifier_definition(self, node: ir.ModifierDefinition):
        self._generate(node)

    @printer.command(name="control-flow-graph")
    @click.option(
        "--name",
        "-n",
        "names",
        type=SolidityName("function", "modifier", case_sensitive=False),
        multiple=True,
        help="Function and modifier names",
    )
    @click.option(
        "-o",
        "--out",
        is_flag=False,
        default=".wake/control-flow-graphs",
        type=click.Path(file_okay=False, dir_okay=True, writable=True),
        help="Output directory",
    )
    @click.option(
        "--direction",
        type=click.Choice(["LR", "TB", "BT", "RL"]),
        default="TB",
        help="Graph direction",
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
    def cli(
        self, names: Tuple[str, ...], out: str, direction: str, links: bool, force: bool
    ) -> None:
        """
        Generate control flow graphs for functions and modifiers.
        """
        self._names = set(names)
        self._out = Path(out).resolve()
        self._out.mkdir(parents=True, exist_ok=True)
        self._direction = direction
        self._links = links
        self._force = force
