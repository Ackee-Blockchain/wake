from __future__ import annotations

from abc import ABCMeta, abstractmethod
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
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
from typing_extensions import Literal

from wake.cli.print import PrintCli, run_print
from wake.core.visitor import Visitor, visit_map
from wake.utils import get_class_that_defined_method

if TYPE_CHECKING:
    from rich.console import Console

    import wake.ir as ir
    from wake.config import WakeConfig


class Printer(Visitor, metaclass=ABCMeta):
    """
    Base class for printers.

    Attributes:
        paths: Paths the printer should operate on. May be empty if a user did not specify any paths, e.g. when running `wake print printer-name`.
            In this case, the printer should operate on all paths. May be ignored unless [visit_mode][wake.printers.api.Printer.visit_mode] is `all`.
        extra: Extra data set by the execution engine.
    """

    console: Console
    paths: List[Path]
    extra: Dict[Any, Any]

    @property
    def visit_mode(self) -> Union[Literal["paths"], Literal["all"]]:
        """
        Configurable visit mode of the printer. If set to `paths`, the printer `visit_` methods will be called only for the paths specified by the user.
        If set to `all`, the printer `visit_` methods will be called for all paths. In this case, the printer should use the `paths` attribute to decide what to print.

        Returns:
            Visit mode of the printer.
        """
        return "paths"

    @abstractmethod
    def print(self) -> None:
        """
        Abstract method that must be implemented in every printer. This method is called after all `visit_` methods have been called.
        """
        ...

    def _run(self) -> None:
        from wake.utils.file_utils import is_relative_to

        for path, source_unit in self.build.source_units.items():
            if (
                self.visit_mode == "all"
                or len(self.paths) == 0
                or any(is_relative_to(path, p) for p in self.paths)
            ):
                for node in source_unit:
                    visit_map[node.ast_node.node_type](self, node)

        self.print()


def get_printers(
    paths: Set[Path], verify_paths: bool
) -> Dict[str, Tuple[click.Command, Type[Printer]]]:
    ret = {}
    for printer_name in run_print.list_commands(
        None,  # pyright: ignore reportGeneralTypeIssues
        plugin_paths=paths,  # pyright: ignore reportGeneralTypeIssues
        force_load_plugins=True,  # pyright: ignore reportGeneralTypeIssues
        verify_paths=verify_paths,  # pyright: ignore reportGeneralTypeIssues
    ):
        command = run_print.get_command(
            None,  # pyright: ignore reportGeneralTypeIssues
            printer_name,
            plugin_paths=paths,  # pyright: ignore reportGeneralTypeIssues
            verify_paths=verify_paths,  # pyright: ignore reportGeneralTypeIssues
        )
        assert command is not None

        cls: Type[Printer] = get_class_that_defined_method(
            command.callback
        )  # pyright: ignore reportGeneralTypeIssues
        if cls is not None:
            ret[printer_name] = (command, cls)
    return ret


async def init_printer(
    config: WakeConfig,
    printer_name: str,
    global_: bool,
    module_name_error_callback: Callable[[str], Awaitable[None]],
    printer_overwrite_callback: Callable[[Path], Awaitable[None]],
    printer_exists_callback: Callable[[str], Awaitable[None]],
    *,
    path: Optional[Path] = None,
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
    if path is not None:
        dir_path = path
    elif global_:
        dir_path = config.global_data_path / "global-printers"
    else:
        dir_path = config.project_root_path / "printers"
    init_path = dir_path / "__init__.py"
    printer_path = dir_path / f"{module_name}.py"

    if printer_path.exists():
        await printer_overwrite_callback(printer_path)
    else:
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
    init_text = init_path.read_text()
    if import_str not in init_text.splitlines():
        with init_path.open("a") as f:
            lines = init_text.splitlines(keepends=True)
            if len(lines) != 0 and not lines[-1].endswith("\n"):
                f.write("\n")
            f.write(f"{import_str}\n")

    return printer_path
