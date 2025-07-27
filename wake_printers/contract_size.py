from __future__ import annotations

from typing import Set, Tuple, List, Dict
import rich_click as click
from rich import print
from rich.table import Table

import wake.ir as ir
from wake.cli import SolidityName
from wake.printers import Printer, printer
from wake.utils import is_relative_to


class ContractSizePrinter(Printer):
    _names: Set[str]
    _show_all: bool
    _show_details: bool
    _show_files: bool
    _sort_by: str
    _table_style: str
    _header_style: str
    _exceeds_style: str
    _ok_style: str

    # EVM size limits
    SPURIOUS_DRAGON_LIMIT = 24576  # 0x6000 - deployed bytecode limit
    SHANGHAI_INITCODE_LIMIT = 49152  # 0xC000 - creation bytecode limit

    def __init__(self):
        self._contract_data: List[Dict] = []
        self._names = set()
        self._show_all = False
        self._show_details = False
        self._show_files = False
        self._sort_by = "runtime"
        self._table_style = "bright_white"
        self._header_style = "bold cyan"
        self._exceeds_style = "bold red"
        self._ok_style = "green"

    def visit_contract_definition(self, node: ir.ContractDefinition):
        # Skip contracts in excluded paths
        if any(
            is_relative_to(node.parent.file, p)
            for p in self.config.compiler.solc.exclude_paths
        ):
            return

        # Filter by contract names if specified
        if len(self._names) > 0 and node.name not in self._names:
            return

        # Skip interfaces and libraries unless --all is specified
        if not self._show_all and node.kind != ir.enums.ContractKind.CONTRACT:
            return

        # Skip if no compilation info
        if not node.compilation_info or not node.compilation_info.evm:
            return

        evm_info = node.compilation_info.evm
        source_unit_name = node.parent.source_unit_name
        contract_data = {
            "name": node.name,
            "kind": node.kind.name.lower(),
            "file": str(source_unit_name),
            "source_unit": str(source_unit_name),  # full source unit name
            "link": self.generate_link(node),
            "creation_size": None,
            "runtime_size": None,
            "creation_exceeds": False,
            "runtime_exceeds": False,
            "has_bytecode": False,
            "has_library_placeholders": False,
            "library_placeholder_count": 0,
        }

        # Analyze creation bytecode (initcode)
        if evm_info.bytecode and evm_info.bytecode.object:
            creation_hex = evm_info.bytecode.object
            creation_size = len(creation_hex) // 2
            contract_data["creation_size"] = creation_size
            contract_data["creation_exceeds"] = (
                creation_size > self.SHANGHAI_INITCODE_LIMIT
            )
            contract_data["has_bytecode"] = True

        # Analyze deployed bytecode (runtime)
        if evm_info.deployed_bytecode and evm_info.deployed_bytecode.object:
            runtime_hex = evm_info.deployed_bytecode.object
            runtime_size = len(runtime_hex) // 2
            contract_data["runtime_size"] = runtime_size
            contract_data["runtime_exceeds"] = runtime_size > self.SPURIOUS_DRAGON_LIMIT
            contract_data["has_bytecode"] = True

        # Only add contracts that have bytecode
        if contract_data["has_bytecode"]:
            self._contract_data.append(contract_data)

    def print(self) -> None:
        if not self._contract_data:
            print("[yellow]No contracts with bytecode found.[/yellow]")
            return

        # Sort contracts based on selected option
        if self._sort_by == "runtime":
            self._contract_data.sort(
                key=lambda x: (-(x["runtime_size"] or 0), x["name"])
            )
        elif self._sort_by == "creation":
            self._contract_data.sort(
                key=lambda x: (-(x["creation_size"] or 0), x["name"])
            )
        elif self._sort_by == "name":
            self._contract_data.sort(key=lambda x: x["name"])
        elif self._sort_by == "file":
            self._contract_data.sort(key=lambda x: (x["source_unit"], x["name"]))

        # Create main table
        table = Table(
            title="📏 Contract Bytecode Sizes vs EVM Limits",
            style=self._table_style,
            show_header=True,
            header_style=self._header_style,
            expand=True,
        )

        table.add_column("Contract", style="bold", no_wrap=True)
        if self._show_files:
            table.add_column("Source", style="dim", max_width=30)
        table.add_column("Type", justify="center", width=8)
        table.add_column("Runtime Size", justify="right", width=12)
        table.add_column("Runtime %", justify="right", width=10)
        table.add_column("Creation Size", justify="right", width=13)
        table.add_column("Creation %", justify="right", width=12)

        if self._show_details:
            table.add_column("File Path", style="dim", max_width=40)

        for contract in self._contract_data:
            name = contract["name"]
            if contract["link"]:
                name = f"[link={contract['link']}]{name}[/link]"

            kind = contract["kind"]

            # Runtime size formatting
            runtime_size = contract["runtime_size"]
            if runtime_size is not None:
                runtime_pct = (runtime_size / self.SPURIOUS_DRAGON_LIMIT) * 100
                runtime_style = (
                    self._exceeds_style
                    if contract["runtime_exceeds"]
                    else self._ok_style
                )
                runtime_str = f"[{runtime_style}]{runtime_size:,}[/{runtime_style}]"
                runtime_pct_str = (
                    f"[{runtime_style}]{runtime_pct:.1f}%[/{runtime_style}]"
                )
            else:
                runtime_str = "[dim]N/A[/dim]"
                runtime_pct_str = "[dim]N/A[/dim]"

            # Creation size formatting
            creation_size = contract["creation_size"]
            if creation_size is not None:
                creation_pct = (creation_size / self.SHANGHAI_INITCODE_LIMIT) * 100
                creation_style = (
                    self._exceeds_style
                    if contract["creation_exceeds"]
                    else self._ok_style
                )
                creation_str = f"[{creation_style}]{creation_size:,}[/{creation_style}]"
                creation_pct_str = (
                    f"[{creation_style}]{creation_pct:.1f}%[/{creation_style}]"
                )
            else:
                creation_str = "[dim]N/A[/dim]"
                creation_pct_str = "[dim]N/A[/dim]"

            row = [name]
            if self._show_files:
                row.append(contract["source_unit"])
            row.extend(
                [kind, runtime_str, runtime_pct_str, creation_str, creation_pct_str]
            )
            if self._show_details:
                row.append(contract["file"])

            table.add_row(*row)

        print(table)

        # Summary statistics
        total_contracts = len(self._contract_data)
        runtime_exceeds = sum(1 for c in self._contract_data if c["runtime_exceeds"])
        creation_exceeds = sum(1 for c in self._contract_data if c["creation_exceeds"])

        print(f"\n📊 Summary:")
        print(f"   Total contracts analyzed: {total_contracts}")
        print(
            f"   Runtime size limit (Spurious Dragon): {self.SPURIOUS_DRAGON_LIMIT:,} bytes"
        )
        print(
            f"   Creation size limit (Shanghai): {self.SHANGHAI_INITCODE_LIMIT:,} bytes"
        )

        if runtime_exceeds > 0:
            print(
                f"   [bold red]⚠️  {runtime_exceeds} contract(s) exceed runtime size limit[/bold red]"
            )
        if creation_exceeds > 0:
            print(
                f"   [bold red]⚠️  {creation_exceeds} contract(s) exceed creation size limit[/bold red]"
            )

        if runtime_exceeds == 0 and creation_exceeds == 0:
            print(
                f"   [bold green]✅ All contracts are within EVM size limits[/bold green]"
            )

    @printer.command(name="contract-size")
    @click.option(
        "--name",
        "-n",
        "names",
        multiple=True,
        type=SolidityName("contract", case_sensitive=False),
        help="Contract names to analyze (can be used multiple times)",
    )
    @click.option(
        "--all",
        "-a",
        "show_all",
        is_flag=True,
        default=False,
        help="Include interfaces and libraries (default: contracts only)",
    )
    @click.option(
        "--details",
        "-d",
        "show_details",
        is_flag=True,
        default=False,
        help="Show detailed information including full file paths",
    )
    @click.option(
        "--files",
        "-f",
        "show_files",
        is_flag=True,
        default=False,
        help="Show full source unit names",
    )
    @click.option(
        "--sort-by",
        "-s",
        "sort_by",
        type=click.Choice(
            ["runtime", "creation", "name", "file"], case_sensitive=False
        ),
        default="runtime",
        help="Sort contracts by: runtime size (default), creation size, name, or file",
    )
    def cli(
        self,
        names: Tuple[str, ...],
        show_all: bool,
        show_details: bool,
        show_files: bool,
        sort_by: str,
    ) -> None:
        """
        Print contract bytecode sizes vs EVM limits.

        Shows both creation bytecode (initcode) and runtime bytecode sizes
        compared to EVM limits:
        - Runtime bytecode: 24,576 bytes (Spurious Dragon limit)
        - Creation bytecode: 49,152 bytes (Shanghai limit)

        Contracts exceeding limits are highlighted in red.
        """
        self._names = set(names)
        self._show_all = show_all
        self._show_details = show_details
        self._show_files = show_files
        self._sort_by = sort_by.lower()
