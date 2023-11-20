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

    import woke.ir as ir


class Printer(Visitor, metaclass=ABCMeta):
    console: Console
    paths: List[Path]

    @abstractmethod
    def print(self) -> None:
        ...

    @classmethod
    def lsp_node(cls) -> Optional[Union[Type[ir.IrAbc], Tuple[Type[ir.IrAbc], ...]]]:
        return None

    def lsp_predicate(self, node: ir.IrAbc) -> bool:
        return True

    def _run(self) -> None:
        from woke.utils.file_utils import is_relative_to

        for path, source_unit in self.build.source_units.items():
            if len(self.paths) == 0 or any(is_relative_to(path, p) for p in self.paths):
                for node in source_unit:
                    visit_map[node.ast_node.node_type](self, node)

        self.print()


def get_printers(
    paths: Set[Path], verify_paths: bool
) -> Dict[str, Tuple[click.Command, Type[Printer]]]:
    ret = {}
    for printer_name in run_print.list_commands(
        None,
        plugin_paths=paths,  # pyright: ignore reportGeneralTypeIssues
        force_load_plugins=True,  # pyright: ignore reportGeneralTypeIssues
        verify_paths=verify_paths,  # pyright: ignore reportGeneralTypeIssues
    ):
        command = run_print.get_command(
            None,
            printer_name,
            plugin_paths=paths,  # pyright: ignore reportGeneralTypeIssues
            verify_paths=verify_paths,  # pyright: ignore reportGeneralTypeIssues
        )

        cls: Type[Printer] = get_class_that_defined_method(
            command.callback
        )  # pyright: ignore reportGeneralTypeIssues
        if cls is not None:
            ret[printer_name] = (command, cls)
    return ret
