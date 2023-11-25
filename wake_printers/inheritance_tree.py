from __future__ import annotations

from typing import Set, Tuple

import networkx as nx
import rich.tree
import rich_click as click
from rich import print

import wake.ir as ir
import wake.ir.types as types
from wake.cli import SolidityName
from wake.printers import Printer, printer


class InheritanceTreePrinter(Printer):
    _names: Set[str]

    def print(self) -> None:
        pass

    def visit_contract_definition(self, node: ir.ContractDefinition):
        from rich.tree import Tree

        def _generate(contract: ir.ContractDefinition, tree: rich.tree.Tree):
            for inheritance_spec in contract.base_contracts:
                base = inheritance_spec.base_name.referenced_declaration
                assert isinstance(base, ir.ContractDefinition)
                tree.add(f"[link={self.generate_link(base)}]{base.name}[/link]")
                _generate(base, tree.children[-1])

            return tree

        if len(self._names) > 0 and node.name not in self._names:
            return

        tree = Tree(
            f"[link={self.generate_link(node)}]{node.name}[/link] inheritance tree"
        )
        _generate(node, tree)
        print(tree, "")

    @printer.command(name="inheritance-tree")
    @click.option(
        "--name",
        "-n",
        "names",
        type=SolidityName("contract", case_sensitive=False),
        multiple=True,
        help="Contract names",
    )
    def cli(self, names: Tuple[str, ...]) -> None:
        """
        Print inheritance tree of contracts.
        """
        self._names = set(names)
