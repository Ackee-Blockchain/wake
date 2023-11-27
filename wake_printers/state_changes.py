from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, List, Set, Tuple, Union

import networkx as nx
import rich_click as click
from rich import print

import wake.ir as ir
import wake.ir.types as types
from wake.cli import SolidityName
from wake.printers import Printer, printer

if TYPE_CHECKING:
    import rich.text


class StateChangesPrinter(Printer):
    _names: Set[str]
    _links: bool

    def print(self) -> None:
        pass

    def _prepare_text(
        self,
        declaration: Union[ir.FunctionDefinition, ir.ModifierDefinition],
        changes: List[
            Tuple[
                Union[ir.ExpressionAbc, ir.StatementAbc, ir.YulAbc],
                ir.enums.ModifiesStateFlag,
            ]
        ],
        text: rich.text.Text,
    ):
        from rich.markup import render
        from rich.style import Style
        from rich.syntax import Syntax

        if len(changes) == 0:
            return

        if isinstance(declaration, ir.FunctionDefinition):
            t = "function"
        else:
            t = "modifier"
        if self._links:
            text.append(
                render(
                    f"  - in {t} [cyan bold link={self.generate_link(declaration)}]{declaration.canonical_name}[/cyan bold link]:\n"
                )
            )
        else:
            text.append(
                render(
                    f"  - in {t} [cyan bold]{declaration.canonical_name}[/cyan bold]:\n"
                )
            )

        for ir_node, mod in sorted(changes, key=lambda x: x[0].byte_location[0]):
            text.append(
                render(
                    f"    - [cyan bold]{repr(mod).replace('_', ' ')}[/cyan bold]\n      "
                )
            )
            syntax = Syntax(ir_node.source, "solidity", dedent=True).highlight(
                ir_node.source
            )
            if self._links and isinstance(syntax.style, Style):
                syntax.style = syntax.style.update_link(self.generate_link(ir_node))
            text.append(syntax)

    def _collect_function_modifies_state(self, node: ir.FunctionDefinition, m: Set):
        if node.body is not None:
            m |= node.body.modifies_state

        for mod_inv in node.modifiers:
            mod = mod_inv.modifier_name.referenced_declaration
            if isinstance(mod, ir.ContractDefinition):
                try:
                    constructor = next(
                        f
                        for f in mod.functions
                        if f.kind == ir.enums.FunctionKind.CONSTRUCTOR
                    )
                    self._collect_function_modifies_state(constructor, m)
                except StopIteration:
                    pass
            elif isinstance(mod, ir.ModifierDefinition):
                if mod.body is not None:
                    m |= mod.body.modifies_state
            else:
                raise AssertionError(f"Unexpected modifier type {type(mod)}")

    def _generate(self, node: Union[ir.FunctionDefinition, ir.ModifierDefinition]):
        from rich.text import Text

        if (
            len(self._names) > 0
            and node.name not in self._names
            and node.canonical_name not in self._names
        ):
            return
        if (
            node.body is None
            or isinstance(node, ir.FunctionDefinition)
            and node.state_mutability
            in {ir.enums.StateMutability.PURE, ir.enums.StateMutability.VIEW}
        ):
            return

        if isinstance(node, ir.FunctionDefinition):
            m = set()
            self._collect_function_modifies_state(node, m)
        else:
            m = node.body.modifies_state

        if len(m) == 0:
            return

        if isinstance(node, ir.FunctionDefinition):
            print("Function", end=" ")
        else:
            print("Modifier", end=" ")

        if self._links:
            print(
                f"[cyan bold link={self.generate_link(node)}]{node.canonical_name}[/cyan bold link] modifies state:"
            )
        else:
            print(f"[cyan bold]{node.canonical_name}[/cyan bold] modifies state:")

        grouped = defaultdict(list)
        for ir_node, mod in m:
            if isinstance(ir_node, ir.ExpressionAbc):
                assert ir_node.statement is not None
                declaration = ir_node.statement.declaration
            elif isinstance(ir_node, ir.StatementAbc):
                declaration = ir_node.declaration
            else:
                declaration = ir_node.inline_assembly.declaration
            grouped[declaration].append((ir_node, mod))

        t = Text()
        this_changes = grouped.pop(node, [])
        self._prepare_text(node, this_changes, t)
        for declaration, changes in grouped.items():
            self._prepare_text(declaration, changes, t)

        print(t)

    def visit_function_definition(self, node: ir.FunctionDefinition):
        self._generate(node)

    def visit_modifier_definition(self, node: ir.ModifierDefinition):
        self._generate(node)

    @printer.command(name="state-changes")
    @click.option(
        "--name",
        "-n",
        "names",
        type=SolidityName("function", "modifier", case_sensitive=False),
        multiple=True,
        help="Function and modifier names",
    )
    @click.option(
        "--links/--no-links",
        default=True,
        help="Generate links to source code",
    )
    def cli(self, names: Tuple[str, ...], links: bool) -> None:
        """
        Print state changes performed by a function/modifier and subsequent calls.
        """
        self._names = set(names)
        self._links = links
