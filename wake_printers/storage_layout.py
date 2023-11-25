from __future__ import annotations

from typing import Set, Tuple

import networkx as nx
import rich_click as click
from rich import print

import wake.ir as ir
import wake.ir.types as types
from wake.cli import SolidityName
from wake.printers import Printer, printer


class StorageLayoutPrinter(Printer):
    _names: Set[str]
    _split_slots: bool
    _table_style: str
    _header_style: str
    _style: str

    def print(self) -> None:
        pass

    def visit_contract_definition(self, node: ir.ContractDefinition):
        from rich.table import Table

        from wake.ir.ast import AstNodeId

        if len(self._names) > 0 and node.name not in self._names:
            return

        assert (
            node.compilation_info is not None
            and node.compilation_info.storage_layout is not None
        ), "Storage layout not available"

        table = Table(title=f"{node.name} storage layout", style=self._table_style)
        table.add_column("Slot", header_style=self._header_style)
        table.add_column("Offset", header_style=self._header_style)
        table.add_column("Name", header_style=self._header_style)
        table.add_column("Type", header_style=self._header_style)
        table.add_column("Contract", header_style=self._header_style)

        last_slot = -1
        for info in node.compilation_info.storage_layout.storage:
            try:
                var = self.build.reference_resolver.resolve_node(
                    AstNodeId(info.ast_id), node.source_unit.cu_hash
                )
                assert isinstance(var, ir.VariableDeclaration)
                label = f"[link={self.generate_link(var)}]{info.label}[/link]"
                type_info = var.type_string

                try:
                    assert isinstance(var.parent, ir.ContractDefinition)
                    contract = f"[link={self.generate_link(var.parent)}]{var.parent.name}[/link]"
                except AssertionError:
                    contract = ""
            except (KeyError, AssertionError):
                label = info.label
                type_info = info.type
                contract = ""

            if info.slot != last_slot:
                if self._split_slots:
                    table.add_section()
                slot = str(info.slot)
            else:
                slot = ""

            table.add_row(
                slot, str(info.offset), label, type_info, contract, style=self._style
            )
            last_slot = info.slot

        print(table)

    @printer.command(name="storage-layout")
    @click.option(
        "--name",
        "-n",
        "names",
        type=SolidityName("contract", case_sensitive=False),
        multiple=True,
        help="Contract names",
    )
    @click.option(
        "--split-slots", is_flag=True, help="Split different slots by a horizontal line"
    )
    @click.option("--table-style", type=str, default="", help="Style for the table.")
    @click.option(
        "--header-style", type=str, default="", help="Style for the table header."
    )
    @click.option(
        "--style", type=str, default="cyan", help="Style for the table cells."
    )
    def cli(
        self,
        names: Tuple[str, ...],
        split_slots: bool,
        table_style: str,
        header_style: str,
        style: str,
    ) -> None:
        """
        Print storage layout of contracts.
        """
        self._names = set(names)
        self._split_slots = split_slots
        self._table_style = table_style
        self._header_style = header_style
        self._style = style
