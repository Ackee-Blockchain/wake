from __future__ import annotations

from typing import TYPE_CHECKING

import networkx as nx
import rich_click as click
from rich import print

import wake.ir as ir
import wake.ir.types as types
from wake.cli import SolidityName
from wake.printers import Printer, printer

if TYPE_CHECKING:
    from typing_extensions import Literal


class LspLinearizedInheritanceGraphPrinter(Printer):
    execution_mode = "lsp"

    _direction: Literal["LR", "RL", "TB", "BT"]
    _urls: bool

    def print(self) -> None:
        pass

    def _generate_graph(self, target_contract: ir.ContractDefinition) -> str:
        import graphviz as gv

        g = gv.Digraph(f"{target_contract.canonical_name} linearized inheritance graph")
        g.attr(rankdir=self._direction)
        g.attr("node", shape="box")

        prev_node_id = None

        for contract in target_contract.linearized_base_contracts:
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
            if prev_node_id is not None:
                g.edge(prev_node_id, node_id)
            prev_node_id = node_id
        return g.source

    def visit_contract_definition(self, node: ir.ContractDefinition):
        from wake.core.lsp_provider import ShowDotCommand

        def on_click() -> None:
            assert self.lsp_provider is not None
            self.lsp_provider.add_commands(
                [
                    ShowDotCommand(
                        title=f"{node.name} linearized inheritance graph",
                        dot=self._generate_graph(node),
                    )
                ]
            )

        assert self.lsp_provider is not None
        self.lsp_provider.add_code_lens(
            node,
            "Linearized inheritance graph",
            on_click=on_click,
        )

    @printer.command(name="lsp-linearized-inheritance-graph")
    @click.option(
        "--direction", type=click.Choice(["LR", "RL", "TB", "BT"]), default="TB"
    )
    @click.option("--urls", is_flag=True, default=True)
    def cli(self, direction: Literal["LR", "RL", "TB", "BT"], urls: bool) -> None:
        self._direction = direction
        self._urls = urls
