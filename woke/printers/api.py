from __future__ import annotations

from abc import ABCMeta, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Tuple, Type, Union

import rich_click as click

from woke.cli.print import run_print
from woke.core.visitor import Visitor, visit_map
from woke.utils import get_class_that_defined_method

if TYPE_CHECKING:
    from rich.console import Console

    from woke.ir import IrAbc


class Printer(Visitor, metaclass=ABCMeta):
    console: Console
    paths: List[Path]
    lsp_node: Optional[Union[Type[IrAbc], Tuple[Type[IrAbc], ...]]] = None

    @abstractmethod
    def print(self) -> None:
        ...

    def lsp_predicate(self, node: IrAbc) -> bool:
        return True

    def _run(self) -> None:
        from woke.utils.file_utils import is_relative_to

        for path, source_unit in self.build.source_units.items():
            if len(self.paths) == 0 or any(is_relative_to(path, p) for p in self.paths):
                for node in source_unit:
                    visit_map[node.ast_node.node_type](self, node)

        self.print()


def get_printers(paths: Set[Path]) -> Dict[str, Tuple[click.Command, Type[Printer]]]:
    ret = {}
    for printer_name in run_print.list_commands(
        None, plugin_paths=paths  # pyright: ignore reportGeneralTypeIssues
    ):
        command = run_print.get_command(
            None,
            printer_name,
            plugin_paths=paths,  # pyright: ignore reportGeneralTypeIssues
        )

        cls: Type[Printer] = get_class_that_defined_method(
            command.callback
        )  # pyright: ignore reportGeneralTypeIssues
        if cls is not None:
            ret[printer_name] = (command, cls)
    return ret
