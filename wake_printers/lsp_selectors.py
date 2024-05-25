from __future__ import annotations

import networkx as nx
import rich_click as click
from rich import print

import wake.ir as ir
import wake.ir.types as types
from wake.cli import SolidityName
from wake.printers import Printer, printer


class LspSelectorsPrinter(Printer):
    execution_mode = "lsp"

    _functions: bool
    _errors: bool
    _events: bool
    _variables: bool

    def print(self) -> None:
        pass

    def _on_click(self, selector: str) -> None:
        from wake.core.lsp_provider import CopyToClipboardCommand, ShowMessageCommand

        assert self.lsp_provider is not None
        self.lsp_provider.add_commands(
            [
                CopyToClipboardCommand(text=selector),
                ShowMessageCommand(message="Copied to clipboard", kind="info"),
            ]
        )

    def visit_function_definition(self, node: ir.FunctionDefinition):
        selector = node.function_selector

        if self._functions and selector is not None:
            assert self.lsp_provider is not None
            self.lsp_provider.add_code_lens(
                node,
                selector.hex(),
                on_click=lambda: self._on_click(selector.hex()),
            )

    def visit_error_definition(self, node: ir.ErrorDefinition):
        if self._errors:
            assert self.lsp_provider is not None
            self.lsp_provider.add_code_lens(
                node,
                node.error_selector.hex(),
                on_click=lambda: self._on_click(node.error_selector.hex()),
            )

    def visit_event_definition(self, node: ir.EventDefinition):
        if self._events:
            assert self.lsp_provider is not None
            self.lsp_provider.add_code_lens(
                node,
                node.event_selector.hex(),
                on_click=lambda: self._on_click(node.event_selector.hex()),
            )

    def visit_variable_declaration(self, node: ir.VariableDeclaration):
        selector = node.function_selector

        if self._variables and selector is not None:
            assert self.lsp_provider is not None
            self.lsp_provider.add_code_lens(
                node,
                selector.hex(),
                on_click=lambda: self._on_click(selector.hex()),
            )

    @printer.command(name="lsp-selectors")
    @click.option(
        "--functions/--no-functions",
        default=True,
        is_flag=True,
        help="Show selectors above functions",
    )
    @click.option(
        "--errors/--no-errors",
        default=True,
        is_flag=True,
        help="Show selectors above errors",
    )
    @click.option(
        "--events/--no-events",
        default=True,
        is_flag=True,
        help="Show selectors above events",
    )
    @click.option(
        "--variables/--no-variables",
        default=True,
        is_flag=True,
        help="Show selectors above public variables",
    )
    def cli(self, functions: bool, errors: bool, events: bool, variables: bool) -> None:
        self._functions = functions
        self._errors = errors
        self._events = events
        self._variables = variables
