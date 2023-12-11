from __future__ import annotations

import asyncio
import logging
import sys
import time
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    AbstractSet,
    Any,
    Dict,
    FrozenSet,
    List,
    Optional,
    Sequence,
    Set,
    Tuple,
    Type,
    Union,
)

import rich_click as click

from wake.core import get_logger
from wake.core.enums import EvmVersionEnum

if TYPE_CHECKING:
    from wake.config import WakeConfig
    from wake.printers import Printer


logger = get_logger(__name__)


class PrintCli(click.RichGroup):  # pyright: ignore reportPrivateImportUsage
    _plugin_commands: Dict[str, click.Command] = {}
    _failed_plugin_paths: Set[Tuple[Path, Exception]] = set()
    _failed_plugin_entry_points: Set[Tuple[str, Exception]] = set()
    _printer_collisions: Set[Tuple[str, str, str]] = set()
    _completion_mode: bool
    _global_data_path: Path
    _plugins_config_path: Path
    _loading_from_plugins: bool = False
    _loading_priorities: Dict[str, Union[str, List[str]]]
    loaded_from_plugins: Dict[str, Union[str, Path]] = {}
    printer_sources: Dict[str, Set[Union[str, Path]]] = {}
    _current_plugin: Union[str, Path] = ""
    _plugins_loaded: bool = False

    def __init__(
        self,
        name: Optional[str] = None,
        commands: Optional[
            Union[Dict[str, click.Command], Sequence[click.Command]]
        ] = None,
        **attrs: Any,
    ):
        super().__init__(name=name, commands=commands, **attrs)

        import os
        import platform

        self._completion_mode = "_WAKE_COMPLETE" in os.environ
        self._loading_priorities = {}

        system = platform.system()

        try:
            self._global_data_path = Path(os.environ["XDG_DATA_HOME"]) / "wake"
        except KeyError:
            if system in {"Linux", "Darwin"}:
                self._global_data_path = Path.home() / ".local" / "share" / "wake"
            elif system == "Windows":
                self._global_data_path = Path(os.environ["LOCALAPPDATA"]) / "wake"
            else:
                raise RuntimeError(f"Unsupported system: {system}")

        try:
            self._plugins_config_path = (
                Path(os.environ["XDG_CONFIG_HOME"]) / "wake" / "plugins.toml"
            )
        except KeyError:
            if system in {"Linux", "Darwin"}:
                self._plugins_config_path = (
                    Path.home() / ".config" / "wake" / "plugins.toml"
                )
            elif system == "Windows":
                self._plugins_config_path = (
                    Path(os.environ["LOCALAPPDATA"]) / "wake" / "plugins.toml"
                )
            else:
                raise RuntimeError(f"Unsupported system: {system}")

        for command in self.commands.values():
            self._inject_params(command)

    @staticmethod
    def _inject_params(command: click.Command) -> None:
        for param in command.params:
            if isinstance(param, click.Option):
                param.show_default = True
                param.show_envvar = True

        command.params.append(
            click.Argument(
                ["paths"],
                nargs=-1,
                type=click.Path(exists=True),
            )
        )

    @property
    def failed_plugin_paths(self) -> FrozenSet[Tuple[Path, Exception]]:
        return frozenset(self._failed_plugin_paths)

    @property
    def failed_plugin_entry_points(self) -> FrozenSet[Tuple[str, Exception]]:
        return frozenset(self._failed_plugin_entry_points)

    @property
    def printer_collisions(self) -> FrozenSet[Tuple[str, str, str]]:
        return frozenset(self._printer_collisions)

    def format_help(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        self.formatter.config.commands_panel_title = "Printers"
        super().format_help(ctx, formatter)
        self.formatter.config.commands_panel_title = "Commands"

    def add_verified_plugin_path(self, path: Path) -> None:
        import tomli
        import tomli_w

        try:
            config = tomli.loads(self._plugins_config_path.read_text())
        except FileNotFoundError:
            config = {}

        if "verified_paths" not in config:
            config["verified_paths"] = []
        else:
            config["verified_paths"] = [
                Path(p).resolve() for p in config["verified_paths"]
            ]

        if path not in config["verified_paths"]:
            config["verified_paths"].append(path)
            config["verified_paths"] = sorted(
                [str(p) for p in config["verified_paths"]]
            )
            self._plugins_config_path.write_text(tomli_w.dumps(config))

    def _verify_plugin_path(self, path: Path) -> bool:
        import tomli
        import tomli_w
        from rich.prompt import Confirm

        if path == self._global_data_path / "global-printers":
            return True

        try:
            config = tomli.loads(self._plugins_config_path.read_text())
        except FileNotFoundError:
            config = {}

        if "verified_paths" not in config:
            config["verified_paths"] = []
        else:
            config["verified_paths"] = [
                Path(p).resolve() for p in config["verified_paths"]
            ]

        if path not in config["verified_paths"]:
            if self._completion_mode:
                return False

            verified = Confirm.ask(f"Do you trust printers in {path}?", default=False)
            if verified:
                config["verified_paths"].append(path)
                config["verified_paths"] = sorted(
                    [str(p) for p in config["verified_paths"]]
                )
                self._plugins_config_path.write_text(tomli_w.dumps(config))
            return verified
        return True

    def _load_plugins(
        self, plugin_paths: AbstractSet[Path], verify_paths: bool
    ) -> None:
        import tomli

        if sys.version_info < (3, 10):
            from importlib_metadata import entry_points
        else:
            from importlib.metadata import entry_points
        from importlib.util import module_from_spec, spec_from_file_location

        self._loading_from_plugins = True
        for cmd in self.loaded_from_plugins.keys():
            self.commands.pop(cmd, None)
        self.loaded_from_plugins.clear()
        self.printer_sources.clear()
        self._failed_plugin_paths.clear()
        self._failed_plugin_entry_points.clear()
        self._printer_collisions.clear()

        try:
            self._loading_priorities = tomli.loads(
                self._plugins_config_path.read_text()
            ).get("printer_loading_priorities", {})
        except FileNotFoundError:
            self._loading_priorities = {}

        printer_entry_points = entry_points().select(group="wake.plugins.printers")
        for entry_point in sorted(printer_entry_points, key=lambda e: e.module):
            self._current_plugin = entry_point.module

            # unload target module and all its children
            for m in [
                k
                for k in sys.modules.keys()
                if k == entry_point.module or k.startswith(entry_point.module + ".")
            ]:
                sys.modules.pop(m)

            try:
                entry_point.load()
            except Exception as e:
                self._failed_plugin_entry_points.add((entry_point.module, e))
                if not self._completion_mode:
                    logger.error(
                        f"Failed to load printers from plugin module '{entry_point.module}': {e}"
                    )

        for path in [self._global_data_path / "global-printers"] + sorted(plugin_paths):
            if not path.exists() or (
                verify_paths and not self._verify_plugin_path(path)
            ):
                continue
            self._current_plugin = path
            sys.path.insert(0, str(path.parent))
            try:
                # unload target module and all its children
                for m in [
                    k
                    for k in sys.modules.keys()
                    if k == path.stem or k.startswith(path.stem + ".")
                ]:
                    sys.modules.pop(m)

                if path.is_dir():
                    spec = spec_from_file_location(path.stem, str(path / "__init__.py"))
                else:
                    spec = spec_from_file_location(path.stem, str(path))

                if spec is not None and spec.loader is not None:
                    module = module_from_spec(spec)
                    spec.loader.exec_module(module)
                else:
                    raise RuntimeError(f"spec_from_file_location returned None")
            except Exception as e:
                self._failed_plugin_paths.add((path, e))
                sys.path.pop(0)
                if not self._completion_mode:
                    logger.error(f"Failed to load printers from path {path}: {e}")

        self._loading_from_plugins = False

    def add_command(self, cmd: click.Command, name: Optional[str] = None) -> None:
        name = name or cmd.name
        assert name is not None
        if name in {"all", "list"}:
            super().add_command(cmd, name)
            return

        if name not in self.printer_sources:
            self.printer_sources[name] = {self._current_plugin}
        else:
            self.printer_sources[name].add(self._current_plugin)

        if name in self._loading_priorities:
            priorities = self._loading_priorities[name]
        elif "*" in self._loading_priorities:
            priorities = self._loading_priorities["*"]
        else:
            priorities = []
        if not isinstance(priorities, list):
            priorities = [priorities]

        if name in self.loaded_from_plugins and isinstance(self._current_plugin, str):
            if isinstance(self.loaded_from_plugins[name], str):
                prev = self.loaded_from_plugins[name]

                # if current plugin is not in priorities and previous plugin is in priorities
                if self._current_plugin not in priorities and prev in priorities:
                    # do not override
                    return

                # if both current and previous plugins are in priorities, but previous is before current
                if (
                    self._current_plugin in priorities
                    and prev in priorities
                    and priorities.index(prev) < priorities.index(self._current_plugin)
                ):
                    # do not override
                    return

        if name in self.loaded_from_plugins:
            if isinstance(self.loaded_from_plugins[name], str):
                prev = f"plugin module '{self.loaded_from_plugins[name]}'"
            else:
                prev = f"path '{self.loaded_from_plugins[name]}'"
            if isinstance(self._current_plugin, str):
                current = f"plugin module '{self._current_plugin}'"
            else:
                current = f"path '{self._current_plugin}'"

            self._printer_collisions.add((name, prev, current))

        self._inject_params(cmd)
        super().add_command(cmd, name)
        if self._loading_from_plugins:
            self.loaded_from_plugins[
                name
            ] = self._current_plugin  # pyright: ignore reportGeneralTypeIssues

    def get_command(
        self,
        ctx: click.Context,
        cmd_name: str,
        plugin_paths: AbstractSet[Path] = frozenset([Path.cwd() / "printers"]),
        force_load_plugins: bool = False,
        verify_paths: bool = True,
    ) -> Optional[click.Command]:
        if not self._plugins_loaded or force_load_plugins:
            self._load_plugins(plugin_paths, verify_paths)
            self._plugins_loaded = True
        return self.commands.get(cmd_name)

    def list_commands(
        self,
        ctx: click.Context,
        plugin_paths: AbstractSet[Path] = frozenset([Path.cwd() / "printers"]),
        force_load_plugins: bool = False,
        verify_paths: bool = True,
    ) -> List[str]:
        if not self._plugins_loaded or force_load_plugins:
            self._load_plugins(plugin_paths, verify_paths)
            self._plugins_loaded = True
        return sorted(self.commands)

    def invoke(self, ctx: click.Context):
        ctx.obj["subcommand_args"] = ctx.args
        ctx.obj["subcommand_protected_args"] = ctx.protected_args
        super().invoke(ctx)


async def print_(
    config: WakeConfig,
    no_artifacts: bool,
    ignore_errors: bool,
    export: Optional[str],
    theme: str,
    watch: bool,
):
    from rich.terminal_theme import DEFAULT_TERMINAL_THEME, SVG_EXPORT_THEME
    from watchdog.observers import Observer

    from ..compiler import SolcOutputSelectionEnum, SolidityCompiler
    from ..compiler.build_data_model import ProjectBuild, ProjectBuildInfo
    from ..compiler.compiler import CompilationFileSystemEventHandler
    from ..compiler.solc_frontend import SolcOutputError, SolcOutputErrorSeverityEnum
    from ..utils import get_class_that_defined_method
    from ..utils.file_utils import is_relative_to
    from .console import console

    ctx = click.get_current_context()
    ctx_args = [*ctx.obj["subcommand_protected_args"][1:], *ctx.obj["subcommand_args"]]

    def callback(build: ProjectBuild, build_info: ProjectBuildInfo):
        errored = any(
            error.severity == SolcOutputErrorSeverityEnum.ERROR
            for info in build_info.compilation_units.values()
            for error in info.errors
        )
        if not ignore_errors and errored:
            if watch:
                return
            else:
                sys.exit(2)

        if export is not None:
            console.record = True

        assert compiler.latest_graph is not None

        assert isinstance(ctx.command, PrintCli)
        assert ctx.invoked_subcommand is not None
        command = ctx.command.get_command(ctx, ctx.invoked_subcommand)
        assert command is not None
        assert command.name is not None

        if hasattr(config.printer, command.name):
            default_map = getattr(config.printer, command.name)
        else:
            default_map = None

        extra = {}
        cls: Type[Printer] = get_class_that_defined_method(
            command.callback
        )  # pyright: ignore reportGeneralTypeIssues
        if cls is not None:

            def _callback(*args, **kwargs):
                instance.paths = [Path(p).resolve() for p in kwargs.pop("paths", [])]

                original_callback(
                    instance, *args, **kwargs
                )  # pyright: ignore reportOptionalCall

            original_callback = command.callback
            command.callback = _callback

            try:
                instance = object.__new__(cls)
                instance.build = build
                instance.build_info = build_info
                instance.config = config
                instance.extra = extra
                instance.console = console
                instance.imports_graph = (  # pyright: ignore reportGeneralTypeIssues
                    compiler.latest_graph.copy()
                )
                instance.logger = get_logger(cls.__name__)
                instance.__init__()

                sub_ctx = command.make_context(
                    command.name,
                    list(ctx_args),
                    parent=ctx,
                    default_map=default_map,
                )
                with sub_ctx:
                    sub_ctx.command.invoke(sub_ctx)

                instance._run()
            except Exception as e:
                if not ignore_errors:
                    raise
                logger.error(f"Error while running printer {command.name}: {e}")
            finally:
                command.callback = original_callback
        else:

            def _callback(*args, **kwargs):
                click.get_current_context().obj["paths"] = [
                    Path(p).resolve() for p in kwargs.pop("paths", [])
                ]

                original_callback(*args, **kwargs)  # pyright: ignore reportOptionalCall

            original_callback = command.callback
            command.callback = _callback
            assert original_callback is not None

            try:
                sub_ctx = command.make_context(
                    command.name, list(ctx_args), parent=ctx, default_map=default_map
                )
                sub_ctx.obj = {
                    "build": build,
                    "build_info": build_info,
                    "config": config,
                    "extra": extra,
                    "console": console,
                    "imports_graph": compiler.latest_graph.copy(),
                    "logger": get_logger(original_callback.__name__),
                }

                with sub_ctx:
                    sub_ctx.command.invoke(sub_ctx)
            except Exception as e:
                if not ignore_errors:
                    raise
                logger.error(f"Error while running printer {command.name}: {e}")
            finally:
                command.callback = original_callback

        if export == "html":
            console.save_html(
                str(config.project_root_path / "wake-print-output.html"),
                theme=SVG_EXPORT_THEME if theme == "dark" else DEFAULT_TERMINAL_THEME,
            )
        elif export == "svg":
            console.save_svg(
                str(config.project_root_path / "wake-print-output.svg"),
                title=f"wake print {command.name}",
                theme=SVG_EXPORT_THEME if theme == "dark" else DEFAULT_TERMINAL_THEME,
            )
        elif export == "text":
            console.save_text(
                str(config.project_root_path / "wake-print-output.txt"),
            )
        elif export == "ansi":
            console.save_text(
                str(config.project_root_path / "wake-print-output.ansi"),
                styles=True,
            )

        console.record = False

    sol_files: Set[Path] = set()
    start = time.perf_counter()
    with console.status("[bold green]Searching for *.sol files...[/]"):
        for file in config.project_root_path.rglob("**/*.sol"):
            if (
                not any(
                    is_relative_to(file, p) for p in config.compiler.solc.exclude_paths
                )
                and file.is_file()
            ):
                sol_files.add(file)
    end = time.perf_counter()
    console.log(
        f"[green]Found {len(sol_files)} *.sol files in [bold green]{end - start:.2f} s[/bold green][/]"
    )

    compiler = SolidityCompiler(config)
    compiler.load(console=console)

    if watch:
        fs_handler = CompilationFileSystemEventHandler(
            config,
            sol_files,
            asyncio.get_event_loop(),
            compiler,
            [SolcOutputSelectionEnum.ALL],
            write_artifacts=not no_artifacts,
            console=console,
            no_warnings=True,
        )
        fs_handler.register_callback(callback)

        observer = Observer()
        observer.schedule(
            fs_handler,
            str(config.project_root_path),
            recursive=True,
        )
        observer.start()
    else:
        fs_handler = None
        observer = None

    build: ProjectBuild
    errors: Set[SolcOutputError]
    build, errors = await compiler.compile(
        sol_files,
        [SolcOutputSelectionEnum.ALL],
        write_artifacts=not no_artifacts,
        console=console,
        no_warnings=True,
    )

    assert compiler.latest_build_info is not None
    callback(build, compiler.latest_build_info)

    if watch:
        assert fs_handler is not None
        assert observer is not None
        try:
            await fs_handler.run()
        except KeyboardInterrupt:
            pass
        finally:
            observer.stop()
            observer.join()

    # prevent execution of a subcommand
    sys.exit(0)


@click.group(
    name="print", cls=PrintCli, context_settings={"auto_envvar_prefix": "WAKE_PRINTER"}
)
@click.option(
    "--no-artifacts", is_flag=True, default=False, help="Do not write build artifacts."
)
@click.option(
    "--ignore-errors",
    is_flag=True,
    default=False,
    help="Ignore compilation errors and run printer anyway.",
)
@click.option(
    "--export",
    type=click.Choice(["svg", "html", "text", "ansi"], case_sensitive=False),
    help="Export output to file.",
)
@click.option(
    "--theme",
    type=click.Choice(["dark", "light"], case_sensitive=False),
    default="dark",
    help="Theme to use for export.",
)
@click.option(
    "--watch",
    "-w",
    is_flag=True,
    default=False,
    help="Watch for changes in the project and re-run on change.",
)
@click.option(
    "--allow-path",
    "allow_paths",
    multiple=True,
    type=click.Path(),
    help="Additional allowed paths for solc.",
    envvar="WAKE_COMPILE_ALLOW_PATHS",
    show_envvar=True,
)
@click.option(
    "--evm-version",
    type=click.Choice(
        ["auto"] + [v.value for v in EvmVersionEnum], case_sensitive=False
    ),
    help="Version of the EVM to compile for. Use 'auto' to let the solc decide.",
    envvar="WAKE_COMPILE_EVM_VERSION",
    show_envvar=True,
)
@click.option(
    "--exclude-path",
    "exclude_paths",
    multiple=True,
    type=click.Path(),
    help="Paths to exclude from compilation unless imported from non-excluded paths.",
    envvar="WAKE_COMPILE_EXCLUDE_PATHS",
    show_envvar=True,
)
@click.option(
    "--include-path",
    "include_paths",
    multiple=True,
    type=click.Path(),
    help="Additional paths to search for when importing *.sol files.",
    envvar="WAKE_COMPILE_INCLUDE_PATHS",
    show_envvar=True,
)
@click.option(
    "--optimizer-enabled/--no-optimizer-enabled",
    is_flag=True,
    required=False,
    default=None,
    help="Enforce optimizer enabled or disabled.",
    envvar="WAKE_COMPILE_OPTIMIZER_ENABLED",
    show_envvar=True,
)
@click.option(
    "--optimizer-runs",
    type=int,
    help="Number of optimizer runs.",
    envvar="WAKE_COMPILE_OPTIMIZER_RUNS",
    show_envvar=True,
)
@click.option(
    "--remapping",
    "remappings",
    multiple=True,
    type=str,
    help="Remappings for solc.",
    envvar="WAKE_COMPILE_REMAPPINGS",
    show_envvar=True,
)
@click.option(
    "--target-version",
    type=str,
    help="Target version of solc used to compile. Use 'auto' to automatically select.",
    envvar="WAKE_COMPILE_TARGET_VERSION",
    show_envvar=True,
)
@click.option(
    "--via-ir/--no-via-ir",
    is_flag=True,
    required=False,
    default=None,
    help="Enforce compilation via IR or not.",
    envvar="WAKE_COMPILE_VIA_IR",
    show_envvar=True,
)
@click.pass_context
def run_print(
    ctx: click.Context,
    no_artifacts: bool,
    ignore_errors: bool,
    export: Optional[str],
    theme: str,
    watch: bool,
    allow_paths: Tuple[str],
    evm_version: Optional[str],
    exclude_paths: Tuple[str],
    include_paths: Tuple[str],
    optimizer_enabled: Optional[bool],
    optimizer_runs: Optional[int],
    remappings: Tuple[str],
    target_version: Optional[str],
    via_ir: Optional[bool],
) -> None:
    """Run a printer."""

    if "--help" in ctx.obj["subcommand_args"]:
        return
    if ctx.invoked_subcommand == "list":
        return

    from ..config import WakeConfig

    config = WakeConfig(local_config_path=ctx.obj.get("local_config_path", None))
    config.load_configs()

    new_options = {}
    deleted_options = []

    if allow_paths:
        new_options["allow_paths"] = allow_paths
    if evm_version is not None:
        if evm_version == "auto":
            deleted_options.append(("compiler", "solc", "evm_version"))
        else:
            new_options["evm_version"] = evm_version
    if exclude_paths:
        new_options["exclude_paths"] = exclude_paths
    if include_paths:
        new_options["include_paths"] = include_paths
    if optimizer_enabled is not None:
        if "optimizer" not in new_options:
            new_options["optimizer"] = {}
        new_options["optimizer"]["enabled"] = optimizer_enabled
    if optimizer_runs is not None:
        if "optimizer" not in new_options:
            new_options["optimizer"] = {}
        new_options["optimizer"]["runs"] = optimizer_runs
    if remappings:
        new_options["remappings"] = remappings
    if target_version is not None:
        if target_version == "auto":
            deleted_options.append(("compiler", "solc", "target_version"))
        else:
            new_options["target_version"] = target_version
    if via_ir is not None:
        new_options["via_IR"] = via_ir

    config.update({"compiler": {"solc": new_options}}, deleted_options)

    asyncio.run(print_(config, no_artifacts, ignore_errors, export, theme, watch))


@run_print.command("list")
@click.pass_context
def run_print_list(ctx):
    """
    List available printers and their sources.
    """

    def normalize_source(source: Union[str, Path]) -> str:
        if isinstance(source, Path):
            if source == Path.cwd() / "printers":
                source = "./printers"
            else:
                try:
                    source = "~/" + str(source.relative_to(Path.home()))
                except ValueError:
                    source = str(source)
        return source

    from rich.table import Table

    from .console import console

    table = Table(title="Available printers")
    table.add_column("Name")
    table.add_column("Loaded from")
    table.add_column("Available in")

    for printer in sorted(
        run_print.list_commands(ctx)  # pyright: ignore reportGeneralTypeIssues
    ):
        if printer in {"all", "list"}:
            continue

        table.add_row(
            printer,
            normalize_source(
                run_print.loaded_from_plugins[  # pyright: ignore reportGeneralTypeIssues
                    printer
                ]
            ),
            ", ".join(
                sorted(
                    normalize_source(s)
                    for s in run_print.printer_sources.get(  # pyright: ignore reportGeneralTypeIssues
                        printer, []
                    )
                )
            ),
        )

    console.print(table)
