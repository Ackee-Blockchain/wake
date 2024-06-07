from __future__ import annotations

from typing import TYPE_CHECKING, Deque, Set, Tuple

import networkx as nx
import rich_click as click
from rich import print

import wake.ir as ir
import wake.ir.types as types
from wake.cli import SolidityName
from wake.printers import Printer, printer

if TYPE_CHECKING:
    from typing_extensions import Literal


class LspInheritanceGraphPrinter(Printer):
    execution_mode = "lsp"

    _direction: Literal["LR", "RL", "TB", "BT"]
    _urls: bool

    def print(self) -> None:
        pass

    def _generate_inheritance_graph(
        self, target_contract: ir.ContractDefinition
    ) -> str:
        from collections import deque

        import graphviz as gv

        queue: Deque[Tuple[ir.ContractDefinition, bool, bool]] = deque(
            [(target_contract, True, True)]
        )
        visited: Set[ir.ContractDefinition] = {target_contract}

        g = gv.Digraph(f"{target_contract.canonical_name} inheritance graph")
        g.attr(rankdir=self._direction)
        g.attr("node", shape="box")

        while len(queue) > 0:
            contract, visit_base, visit_child = queue.popleft()
            node_id = f"{contract.parent.source_unit_name}_{contract.canonical_name}"
            node_attrs = {}
            if contract == target_contract:
                node_attrs["style"] = "filled"

            if self._urls:
                line, column = contract.source_unit.get_line_col_from_byte_offset(
                    contract.name_location[0]
                )
                node_attrs[
                    "URL"
                ] = f"vscode://file/{contract.source_unit.file}:{line}:{column}"

            g.node(node_id, contract.canonical_name, **node_attrs)

            if visit_base:
                for parent in contract.base_contracts:
                    parent_contract = parent.base_name.referenced_declaration
                    assert isinstance(parent_contract, ir.ContractDefinition)
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

    def visit_contract_definition(self, node: ir.ContractDefinition):
        from wake.core.lsp_provider import ShowDotCommand

        def on_click() -> None:
            assert self.lsp_provider is not None
            self.lsp_provider.add_commands(
                [
                    ShowDotCommand(
                        title=f"{node.name} inheritance graph",
                        dot=self._generate_inheritance_graph(node),
                    )
                ]
            )

        assert self.lsp_provider is not None
        self.lsp_provider.add_code_lens(node, "Inheritance graph", on_click=on_click)

    @printer.command(name="lsp-inheritance-graph")
    @click.option(
        "--direction", type=click.Choice(["LR", "RL", "TB", "BT"]), default="BT"
    )
    @click.option("--urls", is_flag=True, default=True)
    def cli(self, direction: Literal["LR", "RL", "TB", "BT"], urls: bool) -> None:
        self._direction = direction
        self._urls = urls
