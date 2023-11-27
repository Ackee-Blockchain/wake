from __future__ import annotations

from typing import Iterable, List, Set, Tuple

import networkx as nx
import rich_click as click
from rich import print

import wake.ir as ir
import wake.ir.types as types
from wake.cli import SolidityName
from wake.printers import Printer, printer


class ModifiersPrinter(Printer):
    _names: Set[str]
    _canonical_names: bool
    _snippets: bool
    _modifiers: List[ir.ModifierDefinition]

    def __init__(self):
        self._modifiers = []

    def _generate_layout(
        self, mod: ir.ModifierDefinition, invocations: Iterable[ir.FunctionDefinition]
    ):
        from os import get_terminal_size

        from rich.columns import Columns
        from rich.markup import render
        from rich.panel import Panel
        from rich.syntax import Syntax

        # Get the terminal size
        terminal_width, _ = get_terminal_size()
        # Calculate the width for each panel
        panel_width = terminal_width // 2 - 1
        # Create a Syntax object for the modifier code with Python syntax highlighting
        code_syntax = Syntax(
            mod.source,
            "solidity",
            dedent=True,
            line_numbers=False,
            tab_size=2,
            word_wrap=True,
        )
        # Create a panel for the modifier code with the calculated width
        mod_name = mod.canonical_name if self._canonical_names else mod.name
        code_panel = Panel(
            code_syntax,
            title=render(f"Modifier [link={self.generate_link(mod)}]{mod_name}[/link]"),
            width=panel_width,
            expand=False,
        )
        # Create a panel for the invocations with the calculated width
        if self._canonical_names:
            invocations_str = "\n".join(
                [
                    f"- [link={self.generate_link(invocation)}]{invocation.canonical_name}[/]"
                    for invocation in invocations
                ]
            )
        else:
            invocations_str = "\n".join(
                [
                    f"- [link={self.generate_link(invocation)}]{invocation.name}[/]"
                    for invocation in invocations
                ]
            )
        invocations_panel = Panel(
            invocations_str, title="Invocations", width=panel_width, expand=False
        )
        # Create a Columns layout with the two panels
        columns = Columns([code_panel, invocations_panel], equal=True, expand=False)

        print(columns)

    def print(self) -> None:
        if not self._snippets:
            for modifier in sorted(self._modifiers, key=lambda m: m.canonical_name):
                functions: Set[ir.FunctionDefinition] = set()
                for ref in modifier.references:
                    if isinstance(ref, ir.IdentifierPathPart):
                        ref = ref.underlying_node
                    elif isinstance(ref, ir.ExternalReference):
                        # should not happen
                        continue
                    p = ref.parent
                    if not isinstance(p, ir.ModifierInvocation):
                        self.logger.warning(
                            f"Unexpected modifier reference parent: {p}\n{p.source}"
                        )
                        continue
                    functions.add(p.parent)

                if len(functions) == 0:
                    print(
                        f"[link={self.generate_link(modifier)}]{modifier.canonical_name}[/link] is not used anywhere"
                    )
                else:
                    print(
                        f"[link={self.generate_link(modifier)}]{modifier.canonical_name}[/link] is used in:"
                    )
                    for function in sorted(functions, key=lambda f: f.canonical_name):
                        print(
                            f"  [link={self.generate_link(function)}]{function.canonical_name}[/link]"
                        )

            return

        for modifier in sorted(self._modifiers, key=lambda m: m.canonical_name):
            functions = set()
            for ref in modifier.references:
                if isinstance(ref, ir.IdentifierPathPart):
                    ref = ref.underlying_node
                elif isinstance(ref, ir.ExternalReference):
                    # should not happen
                    continue
                p = ref.parent
                if not isinstance(p, ir.ModifierInvocation):
                    self.logger.warning(
                        f"Unexpected modifier reference parent: {p}\n{p.source}"
                    )
                    continue
                functions.add(p.parent)
            self._generate_layout(modifier, functions)

    def visit_modifier_definition(self, node: ir.ModifierDefinition):
        if (
            len(self._names) == 0
            or node.name in self._names
            or node.canonical_name in self._names
        ):
            self._modifiers.append(node)

    @printer.command(name="modifiers")
    @click.option(
        "--name",
        "-n",
        "names",
        type=SolidityName("modifier", case_sensitive=False),
        multiple=True,
        help="Modifier names",
    )
    @click.option(
        "--canonical-names/--no-canonical-names",
        default=True,
        help="Use (full) canonical names instead of local names",
    )
    @click.option(
        "--snippets/--no-snippets",
        default=True,
        help="Show code snippets of modifiers",
    )
    def cli(
        self, names: Tuple[str, ...], canonical_names: bool, snippets: bool
    ) -> None:
        """
        Print modifiers and their usage.
        """
        self._names = set(names)
        self._canonical_names = canonical_names
        self._snippets = snippets
