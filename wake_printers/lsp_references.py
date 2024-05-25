from __future__ import annotations

from typing import List, Union

import networkx as nx
import rich_click as click
from rich import print

import wake.ir as ir
import wake.ir.types as types
from wake.cli import SolidityName
from wake.printers import Printer, printer


class LspReferencesPrinter(Printer):
    execution_mode = "lsp"

    _include_declarations: bool
    _local_variables: bool
    _parameter_variables: bool

    def print(self) -> None:
        pass

    def _on_click(
        self,
        declaration: ir.DeclarationAbc,
        references: List[
            Union[
                ir.DeclarationAbc,
                ir.Identifier,
                ir.IdentifierPathPart,
                ir.MemberAccess,
                ir.ExternalReference,
                ir.UnaryOperation,
                ir.BinaryOperation,
            ]
        ],
    ) -> None:
        from wake.core.lsp_provider import GoToLocationsCommand

        locations = []
        for ref in references:
            if isinstance(ref, ir.DeclarationAbc):
                locations.append(
                    (ref.source_unit.file, ref.name_location[0], ref.name_location[1])
                )
            else:
                locations.append(
                    (ref.source_unit.file, ref.byte_location[0], ref.byte_location[1])
                )

        assert self.lsp_provider is not None
        self.lsp_provider.add_commands(
            [
                GoToLocationsCommand.from_offsets(
                    self.build.source_units,
                    declaration.source_unit.file,
                    declaration.name_location[0],
                    locations,
                    "peek",
                    "No references",
                ),
            ]
        )

    def visit_declaration_abc(self, node: ir.DeclarationAbc):
        if isinstance(node, ir.VariableDeclaration):
            if (
                isinstance(node.parent, ir.ParameterList)
                and not self._parameter_variables
            ):
                return
            if (
                isinstance(node.parent, ir.VariableDeclarationStatement)
                and not self._local_variables
            ):
                return

        refs = list(
            node.get_all_references(include_declarations=self._include_declarations)
        )
        refs_count = len(refs)

        assert self.lsp_provider is not None
        self.lsp_provider.add_code_lens(
            node,
            f"{refs_count} reference{'s' if refs_count != 1 else ''}",
            on_click=lambda: self._on_click(node, refs),
        )

    @printer.command(name="lsp-references")
    @click.option(
        "--include-declarations/--no-include-declarations",
        default=False,
        is_flag=True,
        help="Include references to declarations",
    )
    @click.option(
        "--local-variables/--no-local-variables",
        default=True,
        is_flag=True,
        help="Show references above local variables",
    )
    @click.option(
        "--parameter-variables/--no-parameter-variables",
        default=True,
        is_flag=True,
        help="Show references above parameter variables",
    )
    def cli(
        self,
        include_declarations: bool,
        local_variables: bool,
        parameter_variables: bool,
    ) -> None:
        self._include_declarations = include_declarations
        self._local_variables = local_variables
        self._parameter_variables = parameter_variables
