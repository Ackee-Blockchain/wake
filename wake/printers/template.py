TEMPLATE = """from __future__ import annotations

import networkx as nx
import rich_click as click
import wake.ir as ir
import wake.ir.types as types
from rich import print
from wake.cli import SolidityName
from wake.printers import Printer, printer


class {class_name}(Printer):
    def print(self) -> None:
        pass

    @printer.command(name="{command_name}")
    def cli(self) -> None:
        pass
"""
