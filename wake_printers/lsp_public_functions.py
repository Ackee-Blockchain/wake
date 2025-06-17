from __future__ import annotations

from functools import partial

import networkx as nx
import rich_click as click
import wake.ir as ir
import wake.ir.types as types
from rich import print
from wake.cli import SolidityName
from wake.printers import Printer, printer


class LspPublicFunctionsPrinter(Printer):
    execution_mode = "lsp"

    pure: bool
    view: bool

    def print(self) -> None:
        pass

    def _on_click(self, node: ir.ContractDefinition) -> None:
        from wake.core.lsp_provider import GoToLocationsCommand

        functions = {}
        for c in node.linearized_base_contracts:
            for f in c.functions:
                if f.kind in {ir.enums.FunctionKind.RECEIVE, ir.enums.FunctionKind.FALLBACK} and f.kind not in functions:
                    functions[f.kind] = f
                elif f.function_selector is not None and f.function_selector not in functions:
                    functions[f.function_selector] = f

        filtered = [
            f for f in functions.values()
            if f.state_mutability in {ir.enums.StateMutability.NONPAYABLE, ir.enums.StateMutability.PAYABLE} or
            f.state_mutability == ir.enums.StateMutability.PURE and self.pure or
            f.state_mutability == ir.enums.StateMutability.VIEW and self.view
        ]

        self.lsp_provider.add_commands([GoToLocationsCommand.from_nodes(
            node,
            filtered,
            "peek",
            "No public functions",
        )])

    def visit_contract_definition(self, node: ir.ContractDefinition):
        self.lsp_provider.add_code_lens(node, "Public functions", on_click=partial(self._on_click, node))

    @printer.command(name="lsp-public-functions")
    @click.option(
        "--pure/--no-pure",
        default=False,
        help="Include pure functions",
    )
    @click.option(
        "--view/--no-view",
        default=False,
        help="Include view functions",
    )
    def cli(self, pure: bool, view: bool) -> None:
        self.pure = pure
        self.view = view
