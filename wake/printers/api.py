from __future__ import annotations

import logging
from abc import ABCMeta, abstractmethod
from functools import partial
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
from wake.core.visitor import Visitor, group_map, visit_map
from wake.utils import get_class_that_defined_method, is_relative_to

from ..core import get_logger

if TYPE_CHECKING:
    import threading

    import networkx as nx
    from rich.console import Console

    import wake.ir as ir
    from wake.compiler.build_data_model import ProjectBuild, ProjectBuildInfo
    from wake.config import WakeConfig
    from wake.core.lsp_provider import LspProvider


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
    lsp_provider: Optional[LspProvider]
    execution_mode: Literal["cli", "lsp", "both"] = "cli"  # TODO remove both?

    @property
    def visit_mode(self) -> Literal["paths", "all"]:
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


def run_printers(
    printer_names: Union[str, List[str]],
    build: ProjectBuild,
    build_info: ProjectBuildInfo,
    imports_graph: nx.DiGraph,
    config: WakeConfig,
    console: Console,
    ctx: Optional[click.Context],
    lsp_provider: Optional[LspProvider],
    *,
    paths: Optional[List[Path]] = None,
    args: Optional[List[str]] = None,
    verify_paths: bool = True,
    capture_exceptions: bool = False,
    logging_handler: Optional[logging.Handler] = None,
    extra: Optional[Dict[Any, Any]] = None,
    cancel_event: Optional[threading.Event] = None,
):
    from wake.core.exceptions import ThreadCancelledError
    from wake.utils import get_package_version

    if extra is None:
        extra = {}
    if "package_versions" not in extra:
        extra["package_versions"] = {}
    extra["package_versions"]["eth-wake"] = get_package_version("eth-wake")

    exceptions = {}

    printers: List[click.Command] = []
    if isinstance(printer_names, str):
        command = run_print.get_command(
            ctx,  # pyright: ignore reportGeneralTypeIssues
            printer_names,
            plugin_paths={  # pyright: ignore reportGeneralTypeIssues
                config.project_root_path / "printers"
            },
            verify_paths=verify_paths,  # pyright: ignore reportGeneralTypeIssues
        )
        try:
            assert command is not None, f"Printer {printer_names} not found"
            printers.append(command)
        except AssertionError as e:
            if not capture_exceptions:
                raise
            exceptions[printer_names] = e
    elif isinstance(printer_names, list):
        if config.printers.only is None:
            only = set(printer_names)
        else:
            only = set(config.printers.only)

        for printer_name in printer_names:
            if (
                printer_name not in only
                or printer_name in config.printers.exclude
                or printer_name == "list"
            ):
                continue

            command = run_print.get_command(
                None,  # pyright: ignore reportGeneralTypeIssues
                printer_name,
                plugin_paths={  # pyright: ignore reportGeneralTypeIssues
                    config.project_root_path / "printers"
                },
                verify_paths=verify_paths,  # pyright: ignore reportGeneralTypeIssues
            )
            try:
                assert command is not None, f"Printer {printer_name} not found"
                printers.append(command)
            except AssertionError as e:
                if not capture_exceptions:
                    raise
                exceptions[printer_name] = e

    if args is None:
        args = []

    collected_printers: Dict[str, Printer] = {}
    visit_all_printers: Set[str] = set()

    for command in list(printers):
        if cancel_event is not None and cancel_event.is_set():
            raise ThreadCancelledError()

        assert command is not None
        assert command.name is not None

        if lsp_provider is not None:
            lsp_provider._current_sort_tag = command.name

        if hasattr(config.printer, command.name):
            default_map = getattr(config.printer, command.name)
        else:
            default_map = None

        cls: Type[Printer] = get_class_that_defined_method(
            command.callback
        )  # pyright: ignore reportGeneralTypeIssues
        if cls is not None:

            def _callback(  # pyright: ignore reportGeneralTypeIssues
                printer_name: str, *args, **kwargs
            ):
                nonlocal paths
                if paths is None:
                    paths = [Path(p).resolve() for p in kwargs.pop("paths", [])]
                else:
                    kwargs.pop("paths", None)

                instance.paths = [Path(p).resolve() for p in paths]
                original_callback(
                    instance, *args, **kwargs
                )  # pyright: ignore reportOptionalCall

            original_callback = command.callback
            command.callback = partial(_callback, command.name)

            if lsp_provider is not None and cls.execution_mode == "cli":
                printers.remove(command)
                continue
            elif lsp_provider is None and cls.execution_mode == "lsp":
                printers.remove(command)
                continue

            try:
                instance = object.__new__(cls)
                instance.build = build
                instance.build_info = build_info
                instance.config = config
                instance.extra = extra
                instance.console = console
                instance.imports_graph = (
                    imports_graph.copy()
                )  # pyright: ignore reportGeneralTypeIssues
                instance.lsp_provider = lsp_provider
                instance.logger = get_logger(cls.__name__)
                if logging_handler is not None:
                    instance.logger.addHandler(logging_handler)

                try:
                    instance.__init__()

                    sub_ctx = command.make_context(
                        command.name,
                        list(args),
                        parent=ctx,
                        default_map=default_map,
                    )
                    with sub_ctx:
                        sub_ctx.command.invoke(sub_ctx)

                    collected_printers[command.name] = instance
                    if instance.visit_mode == "all":
                        visit_all_printers.add(command.name)
                except Exception:
                    if logging_handler is not None:
                        instance.logger.removeHandler(logging_handler)
                    raise
            except Exception as e:
                if not capture_exceptions:
                    raise
                exceptions[command.name] = e
            finally:
                command.callback = original_callback
        else:
            if lsp_provider is not None:
                printers.remove(command)
                continue

            def _callback(printer_name: str, *args, **kwargs):
                nonlocal paths
                if paths is None:
                    paths = [Path(p).resolve() for p in kwargs.pop("paths", [])]
                else:
                    kwargs.pop("paths", None)

                click.get_current_context().obj["paths"] = [
                    Path(p).resolve() for p in paths
                ]

                return original_callback(
                    *args, **kwargs
                )  # pyright: ignore reportOptionalCall

            original_callback = command.callback
            command.callback = partial(_callback, command.name)
            assert original_callback is not None

            try:
                sub_ctx = command.make_context(
                    command.name, list(args), parent=ctx, default_map=default_map
                )
                sub_ctx.obj = {
                    "build": build,
                    "build_info": build_info,
                    "config": config,
                    "extra": extra,
                    "imports_graph": imports_graph.copy(),
                    "logger": get_logger(original_callback.__name__),
                    "console": console,
                    # no need to set lsp_provider as legacy printers are not executed by the LSP server
                }
                if logging_handler is not None:
                    sub_ctx.obj[
                        "logger"
                    ].addHandler(  # pyright: ignore reportGeneralTypeIssues
                        logging_handler
                    )

                try:
                    with sub_ctx:
                        sub_ctx.command.invoke(sub_ctx)
                finally:
                    if logging_handler is not None:
                        sub_ctx.obj[
                            "logger"
                        ].removeHandler(  # pyright: ignore reportGeneralTypeIssues
                            logging_handler
                        )
            except Exception as e:
                if not capture_exceptions:
                    raise
                exceptions[command.name] = e
            finally:
                command.callback = original_callback

    if paths is None:
        paths = []

    for path, source_unit in build.source_units.items():
        if cancel_event is not None and cancel_event.is_set():
            raise ThreadCancelledError()

        # TODO config printers ignore paths

        target_printers = visit_all_printers
        if len(paths) == 0 or any(is_relative_to(path, p) for p in paths):
            target_printers = collected_printers.keys()

        if len(target_printers) == 0:
            continue

        for node in source_unit:
            for printer_name in list(target_printers):
                if lsp_provider is not None:
                    lsp_provider._current_sort_tag = printer_name

                printer = collected_printers[printer_name]
                try:
                    printer.visit_ir_abc(node)
                    if node.ast_node.node_type in group_map:
                        for group in group_map[node.ast_node.node_type]:
                            visit_map[group](printer, node)
                    visit_map[node.ast_node.node_type](printer, node)
                except Exception as e:
                    if not capture_exceptions:
                        raise
                    exceptions[printer_name] = e
                    if logging_handler is not None:
                        printer.logger.removeHandler(logging_handler)
                    del collected_printers[printer_name]

    for printer_name, printer in collected_printers.items():
        if cancel_event is not None and cancel_event.is_set():
            raise ThreadCancelledError()

        if lsp_provider is not None:
            lsp_provider._current_sort_tag = printer_name

        try:
            printer.print()
        except Exception as e:
            if not capture_exceptions:
                raise
            exceptions[printer_name] = e
        finally:
            if logging_handler is not None:
                printer.logger.removeHandler(logging_handler)

    return printers, exceptions
