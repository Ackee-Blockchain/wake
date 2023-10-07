from __future__ import annotations

from abc import ABCMeta, abstractmethod
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Awaitable,
    Callable,
    Dict,
    List,
    Optional,
    Set,
    Tuple,
    Type,
    Union,
)

import rich_click as click

from woke.cli.print import PrintCli, run_print
from woke.core.visitor import Visitor, visit_map
from woke.utils import get_class_that_defined_method

if TYPE_CHECKING:
    from rich.console import Console

    import woke.ir as ir
    from woke.config import WokeConfig


class Printer(Visitor, metaclass=ABCMeta):
    console: Console
    paths: List[Path]

    @abstractmethod
    def print(self) -> None:
        ...

    @classmethod
    def lsp_node(cls) -> Optional[Union[Type[ir.IrAbc], Tuple[Type[ir.IrAbc], ...]]]:
        return None

    def lsp_name(self) -> Optional[str]:
        # return None for the default name (name of the Click command), empty string to skip
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


async def init_printer(
    config: WokeConfig,
    printer_name: str,
    global_: bool,
    module_name_error_callback: Callable[[str], Awaitable[None]],
    printer_exists_callback: Callable[[str], Awaitable[None]],
) -> Path:
    from .template import TEMPLATE

    assert isinstance(run_print, PrintCli)

    module_name = printer_name.replace("-", "_")
    if not module_name.isidentifier():
        await module_name_error_callback(module_name)
        # unreachable
        raise ValueError(
            f"Printer name must be a valid Python identifier, got {printer_name}"
        )

    class_name = (
        "".join([s.capitalize() for s in module_name.split("_") if s != ""]) + "Printer"
    )
    if global_:
        dir_path = config.global_data_path / "global-printers"
    else:
        dir_path = config.project_root_path / "printers"
    init_path = dir_path / "__init__.py"
    printer_path = dir_path / f"{module_name}.py"

    if printer_name in run_print.loaded_from_plugins:
        if isinstance(run_print.loaded_from_plugins[printer_name], str):
            other = f"package '{run_print.loaded_from_plugins[printer_name]}'"
        else:
            other = f"path '{run_print.loaded_from_plugins[printer_name]}'"
        await printer_exists_callback(other)

    if not dir_path.exists():
        dir_path.mkdir()
        run_print.add_verified_plugin_path(dir_path)

    printer_path.write_text(
        TEMPLATE.format(class_name=class_name, command_name=printer_name)
    )

    if not init_path.exists():
        init_path.touch()

    import_str = f"from .{module_name} import {class_name}"
    if import_str not in init_path.read_text().splitlines():
        with init_path.open("a") as f:
            f.write(f"\n{import_str}")

    return printer_path
