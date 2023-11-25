from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import List, Set, Tuple

import networkx as nx
import rich_click as click
from rich import print

import wake.ir as ir
import wake.ir.types as types
from wake.cli import SolidityName
from wake.printers import Printer, printer


class InheritanceGraphPrinter(Printer):
    _names: Set[str]
    _out: Path
    _direction: str
    _links: bool
    _force: bool
    _single_file: bool
    _children: bool
    _parents: bool
    _interfaces: bool
    _contracts: List[ir.ContractDefinition]

    def __init__(self):
        self._contracts = []

    def _generate(self, contracts: List[ir.ContractDefinition]):
        import graphviz as gv

        g = gv.Digraph(
            f"{contracts[0].name} inheritance graph"
            if len(contracts) == 1
            else "Inheritance graph"
        )
        g.attr(rankdir=self._direction)
        g.attr("node", shape="box")

        visited = set(contracts)
        queue = deque((c, self._parents, self._children) for c in contracts)
        edges: Set[Tuple[str, str]] = set()

        while len(queue) != 0:
            contract, visit_base, visit_child = queue.popleft()
            node_id = f"{contract.parent.source_unit_name}_{contract.name}"
            node_attrs = {}
            if [contract] == contracts:
                node_attrs["style"] = "filled"
            if self._links:
                node_attrs["URL"] = self.generate_link(contract)

            g.node(node_id, contract.name, **node_attrs)

            for modifier_inv in contract.base_contracts:
                parent = modifier_inv.base_name.referenced_declaration
                assert isinstance(parent, ir.ContractDefinition)

                if (
                    visit_base
                    and (
                        self._interfaces
                        or parent.kind != ir.enums.ContractKind.INTERFACE
                    )
                ) or parent in contracts:
                    edges.add(
                        (
                            node_id,
                            f"{parent.parent.source_unit_name}_{parent.name}",
                        )
                    )
                    if parent not in visited:
                        visited.add(parent)
                        queue.append((parent, True, False))

            for child in contract.child_contracts:
                if (
                    visit_child
                    and (
                        self._interfaces
                        or child.kind != ir.enums.ContractKind.INTERFACE
                    )
                ) or child in contracts:
                    edges.add(
                        (
                            f"{child.parent.source_unit_name}_{child.name}",
                            node_id,
                        )
                    )
                    if child not in visited:
                        visited.add(child)
                        queue.append((child, False, True))

        for from_, to in edges:
            g.edge(from_, to)

        return g

    def print(self) -> None:
        if self._single_file:
            g = self._generate(self._contracts)
            p = self._out / "inheritance-graph.dot"
            if not self._force and p.exists():
                self.logger.warning(f"File {p} already exists, skipping")
                return
            g.save(p)
        else:
            for contract in self._contracts:
                g = self._generate([contract])
                p = self._out / f"{contract.name}.dot"
                if not self._force and p.exists():
                    self.logger.warning(f"File {p} already exists, skipping")
                    continue
                g.save(p)

    def visit_contract_definition(self, node: ir.ContractDefinition):
        if len(self._names) == 0 or node.name in self._names:
            self._contracts.append(node)

    @printer.command(name="inheritance-graph")
    @click.option(
        "--name",
        "-n",
        "names",
        type=SolidityName("contract", case_sensitive=False),
        multiple=True,
        help="Contract names",
    )
    @click.option(
        "-o",
        "--out",
        is_flag=False,
        default=".wake/inheritance-graphs",
        type=click.Path(file_okay=False, dir_okay=True, writable=True),
        help="Output directory",
    )
    @click.option(
        "--direction",
        type=click.Choice(["LR", "TB", "BT", "RL"]),
        default="BT",
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
    @click.option(
        "--children/--no-children",
        default=True,
        help="Generate contract children",
    )
    @click.option(
        "--parents/--no-parents",
        default=True,
        help="Generate contract parents",
    )
    @click.option(
        "--interfaces/--no-interfaces",
        default=True,
        help="Generate interfaces",
    )
    @click.option(
        "--single-file/--multiple-files",
        default=True,
        help="Generate single with all discovered contracts or multiple files per contract",
    )
    def cli(
        self,
        names: Tuple[str, ...],
        out: str,
        direction: str,
        links: bool,
        force: bool,
        children: bool,
        parents: bool,
        interfaces: bool,
        single_file: bool,
    ) -> None:
        """
        Generate inheritance graphs for contracts.
        """
        self._names = set(names)
        self._out = Path(out).resolve()
        self._out.mkdir(parents=True, exist_ok=True)
        self._direction = direction
        self._links = links
        self._force = force
        self._children = children
        self._parents = parents
        self._interfaces = interfaces
        self._single_file = single_file
