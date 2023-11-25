from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import networkx as nx
import rich_click as click
from rich import print

import wake.ir as ir
import wake.ir.types as types
from wake.cli import SolidityName
from wake.printers import Printer, printer


class AbiPrinter(Printer):
    _names: Set[str]
    _out: Optional[Path]
    _skip_empty: bool
    _abi: Dict[ir.ContractDefinition, List]

    def __init__(self):
        self._abi = {}

    def print(self) -> None:
        import json

        for contract in sorted(self._abi.keys(), key=lambda c: c.name):
            abi = self._abi[contract]

            if self._out is None:
                print(
                    f"ABI for [link={self.generate_link(contract)}]{contract.parent.source_unit_name}:{contract.name}[/link]:"
                )
                self.console.print_json(data=abi)
            else:
                if len([c for c in self._abi.keys() if c.name == contract.name]) > 1:
                    source_unit_name_path = Path(contract.parent.source_unit_name)
                    if source_unit_name_path.is_absolute():
                        self.logger.warning(
                            f"Cannot generate ABI for duplicate contract [link={self.generate_link(contract)}]{contract.name}[/link] with absolute source unit name {contract.parent.source_unit_name}"
                        )
                        continue
                    p = self._out.joinpath(source_unit_name_path)
                    p.mkdir(parents=True, exist_ok=True)
                    p.joinpath(f"{contract.name}.abi.json").write_text(
                        json.dumps(abi, indent=4)
                    )
                else:
                    self._out.joinpath(f"{contract.name}.abi.json").write_text(
                        json.dumps(abi, indent=4)
                    )

    def visit_contract_definition(self, node: ir.ContractDefinition):
        if len(self._names) > 0 and node.name not in self._names:
            return
        if node.compilation_info is None or node.compilation_info.abi is None:
            self.logger.warning(
                f"ABI for [link={self.generate_link(node)}]{node.parent.source_unit_name}:{node.name}[/link] not available"
            )
            return

        if self._skip_empty and len(node.compilation_info.abi) == 0:
            return

        self._abi[node] = node.compilation_info.abi

    @printer.command(name="abi")
    @click.option(
        "--name",
        "-n",
        "names",
        type=SolidityName("contract", case_sensitive=False),
        multiple=True,
        help="Contract names",
    )
    @click.option(
        "-o",
        "--out",
        is_flag=False,
        flag_value="abi",
        default=None,
        type=click.Path(file_okay=False, dir_okay=True, writable=True),
        help="Export ABI into the specified directory",
    )
    @click.option(
        "-s",
        "--skip-empty",
        is_flag=True,
        default=False,
        help="Skip contracts with empty ABI",
    )
    def cli(self, names: Tuple[str, ...], out: Optional[str], skip_empty: bool) -> None:
        """
        Print ABI of contracts.
        """
        self._names = set(names)
        self._skip_empty = skip_empty
        if out is not None:
            self._out = Path(out)
            self._out.mkdir(parents=True, exist_ok=True)
        else:
            self._out = None
