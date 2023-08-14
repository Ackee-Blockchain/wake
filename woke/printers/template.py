TEMPLATE = """from __future__ import annotations

import rich_click as click
import woke.ir as ir
import woke.ir.types as types
from woke.printers import Printer, printer


class {class_name}(Printer):
    def print(self) -> None:
        pass

    @printer.command(name="{command_name}")
    def cli(self) -> None:
        pass
"""
