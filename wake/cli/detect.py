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
    Iterable,
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
    from wake.detectors import (
        Detection,
        Detector,
        DetectorConfidence,
        DetectorImpact,
        DetectorResult,
    )

logger = get_logger(__name__)


class DetectCli(click.RichGroup):  # pyright: ignore reportPrivateImportUsage
    _plugin_commands: Dict[str, click.Command] = {}
    _failed_plugin_paths: Set[Tuple[Path, Exception]] = set()
    _failed_plugin_entry_points: Set[Tuple[str, Exception]] = set()
    _detector_collisions: Set[Tuple[str, str, str]] = set()
    _completion_mode: bool
    _global_data_path: Path
    _plugins_config_path: Path
    _loading_from_plugins: bool = False
    _loading_priorities: Dict[str, Union[str, List[str]]]
    loaded_from_plugins: Dict[str, Union[str, Path]] = {}
    detector_sources: Dict[str, Set[Union[str, Path]]] = {}
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
        command.params.append(
            click.Option(
                ["--min-impact"],
                type=click.Choice(["info", "warning", "low", "medium", "high"]),
                default="info",
                help="Minimum impact level to report",
                show_default=True,
                show_envvar=True,
            )
        )
        command.params.append(
            click.Option(
                ["--min-confidence"],
                type=click.Choice(["low", "medium", "high"]),
                default="low",
                help="Minimum confidence level to report",
                show_default=True,
                show_envvar=True,
            )
        )

    @property
    def failed_plugin_paths(self) -> FrozenSet[Tuple[Path, Exception]]:
        return frozenset(self._failed_plugin_paths)

    @property
    def failed_plugin_entry_points(self) -> FrozenSet[Tuple[str, Exception]]:
        return frozenset(self._failed_plugin_entry_points)

    @property
    def detector_collisions(self) -> FrozenSet[Tuple[str, str, str]]:
        return frozenset(self._detector_collisions)

    def format_help(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        formatter.config.commands_panel_title = "Detectors"
        super().format_help(ctx, formatter)
        formatter.config.commands_panel_title = "Commands"

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

        if path == self._global_data_path / "global-detectors":
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

            verified = Confirm.ask(f"Do you trust detectors in {path}?", default=False)
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
        self.detector_sources.clear()
        self._failed_plugin_paths.clear()
        self._failed_plugin_entry_points.clear()
        self._detector_collisions.clear()

        try:
            self._loading_priorities = tomli.loads(
                self._plugins_config_path.read_text()
            ).get("detector_loading_priorities", {})
        except FileNotFoundError:
            self._loading_priorities = {}

        detector_entry_points = entry_points().select(group="wake.plugins.detectors")
        for entry_point in sorted(detector_entry_points, key=lambda e: e.module):
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
                        f"Failed to load detectors from plugin module '{entry_point.module}': {e}"
                    )

        for path in [self._global_data_path / "global-detectors"] + sorted(
            plugin_paths
        ):
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
                    for k in sys.modules
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
                    logger.error(f"Failed to load detectors from path {path}: {e}")

        self._loading_from_plugins = False

    def add_command(self, cmd: click.Command, name: Optional[str] = None) -> None:
        name = name or cmd.name
        assert name is not None
        if name in {"all", "list"}:
            if name == "all":
                self._inject_params(cmd)
            super().add_command(cmd, name)
            return

        if name not in self.detector_sources:
            self.detector_sources[name] = {self._current_plugin}
        else:
            self.detector_sources[name].add(self._current_plugin)

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

            self._detector_collisions.add((name, prev, current))

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
        plugin_paths: AbstractSet[Path] = frozenset([Path.cwd() / "detectors"]),
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
        plugin_paths: AbstractSet[Path] = frozenset([Path.cwd() / "detectors"]),
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


async def detect_(
    config: WakeConfig,
    no_artifacts: bool,
    ignore_errors: bool,
    export: Optional[str],
    theme: str,
    watch: bool,
    ignore_disable_overrides: bool,
):
    import os

    from jschema_to_python.to_json import to_json
    from rich.terminal_theme import DEFAULT_TERMINAL_THEME, SVG_EXPORT_THEME
    from watchdog.observers import Observer

    from wake.detectors.api import (
        DetectorConfidence,
        DetectorImpact,
        detect,
        print_detection,
    )
    from wake.detectors.utils import create_sarif_log

    from ..compiler import SolcOutputSelectionEnum, SolidityCompiler
    from ..compiler.build_data_model import ProjectBuild, ProjectBuildInfo
    from ..compiler.compiler import CompilationFileSystemEventHandler
    from ..compiler.solc_frontend import SolcOutputError, SolcOutputErrorSeverityEnum
    from ..utils.file_utils import is_relative_to
    from .console import console

    severity_map: Dict[DetectorImpact, Dict[DetectorConfidence, int]] = {
        DetectorImpact.HIGH: {
            DetectorConfidence.HIGH: 0,
            DetectorConfidence.MEDIUM: 1,
            DetectorConfidence.LOW: 2,
        },
        DetectorImpact.MEDIUM: {
            DetectorConfidence.HIGH: 1,
            DetectorConfidence.MEDIUM: 2,
            DetectorConfidence.LOW: 3,
        },
        DetectorImpact.LOW: {
            DetectorConfidence.HIGH: 2,
            DetectorConfidence.MEDIUM: 3,
            DetectorConfidence.LOW: 4,
        },
        DetectorImpact.WARNING: {
            DetectorConfidence.HIGH: 5,
            DetectorConfidence.MEDIUM: 6,
            DetectorConfidence.LOW: 7,
        },
        DetectorImpact.INFO: {
            DetectorConfidence.HIGH: 8,
            DetectorConfidence.MEDIUM: 9,
            DetectorConfidence.LOW: 10,
        },
    }

    default_min_impact = os.getenv("WAKE_DETECT_MIN_IMPACT", DetectorImpact.INFO)
    if default_min_impact.lower() not in DetectorImpact.__members__.values():
        raise click.BadParameter(
            f"Invalid value for WAKE_DETECT_MIN_IMPACT environment variable: {default_min_impact}"
        )
    default_min_confidence = os.getenv(
        "WAKE_DETECT_MIN_CONFIDENCE", DetectorConfidence.LOW
    )
    if default_min_confidence.lower() not in DetectorConfidence.__members__.values():
        raise click.BadParameter(
            f"Invalid value for WAKE_DETECT_MIN_CONFIDENCE environment variable: {default_min_confidence}"
        )

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

        assert compiler.latest_graph is not None
        assert ctx.invoked_subcommand is not None
        if ctx.invoked_subcommand == "all":
            detectors = run_detect.list_commands(ctx)

            for detector_name in config.detectors.exclude.union(
                config.detectors.only or set()
            ):
                if detector_name not in detectors:
                    logger.warning(f"Detector {detector_name} not found")
        else:
            detectors = ctx.invoked_subcommand

        used_detectors, detections, exceptions = detect(
            detectors,
            build,
            build_info,
            compiler.latest_graph,
            config,
            ctx,
            None,
            args=list(ctx_args),
            console=console,
            capture_exceptions=ignore_errors,
            default_min_impact=default_min_impact,  # pyright: ignore reportGeneralTypeIssues
            default_min_confidence=default_min_confidence,  # pyright: ignore reportGeneralTypeIssues
            extra={"lsp": False},
        )

        if ignore_errors:
            for detector_name, exception in exceptions.items():
                logger.error(
                    f"Error while running detector {detector_name}: {exception}"
                )

        if export is not None:
            console.record = True

        all_detections: List[Tuple[str, DetectorResult]] = []
        for detector_name in detections.keys():
            for d in detections[detector_name][0]:
                all_detections.append((detector_name, d))
            if ignore_disable_overrides:
                for d in detections[detector_name][1]:
                    all_detections.append((detector_name, d))

        all_detections.sort(
            key=lambda d: (
                severity_map[d[1].impact][d[1].confidence],
                d[1].detection.ir_node.source_unit.source_unit_name,
                d[1].detection.ir_node.byte_location[0],
                d[1].detection.ir_node.byte_location[1],
            )
        )

        for detector_name, detection in all_detections:
            print_detection(
                detector_name,
                detection,
                config,
                console,
                "monokai" if theme == "dark" else "default",
            )

        if len(all_detections) == 0:
            console.print("No detections found")

        if export == "html":
            console.save_html(
                str(config.project_root_path / "wake-detections.html"),
                theme=SVG_EXPORT_THEME if theme == "dark" else DEFAULT_TERMINAL_THEME,
            )
        elif export == "svg":
            console.save_svg(
                str(config.project_root_path / "wake-detections.svg"),
                title=f"wake detect {ctx.invoked_subcommand}",
                theme=SVG_EXPORT_THEME if theme == "dark" else DEFAULT_TERMINAL_THEME,
            )
        elif export == "text":
            console.save_text(
                str(config.project_root_path / "wake-detections.txt"),
            )
        elif export == "ansi":
            console.save_text(
                str(config.project_root_path / "wake-detections.ansi"),
                styles=True,
            )
        elif export == "sarif":
            log = create_sarif_log(used_detectors, all_detections)
            (config.project_root_path / "wake-detections.sarif").write_text(
                to_json(log)
            )

        console.record = False

        if not watch:
            sys.exit(0 if len(all_detections) == 0 else 3)

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
    name="detect",
    cls=DetectCli,
    context_settings={"auto_envvar_prefix": "WAKE_DETECTOR"},
)
@click.option(
    "--no-artifacts", is_flag=True, default=False, help="Do not write build artifacts."
)
@click.option(
    "--ignore-errors",
    is_flag=True,
    default=False,
    help="Ignore compilation errors and detector exceptions.",
)
@click.option(
    "--export",
    type=click.Choice(["svg", "html", "text", "ansi", "sarif"], case_sensitive=False),
    help="Export detections to file.",
)
@click.option(
    "--theme",
    type=click.Choice(["dark", "light"], case_sensitive=False),
    default="dark",
    help="Theme for printing detections.",
)
@click.option(
    "--watch",
    "-w",
    is_flag=True,
    default=False,
    help="Watch for changes in the project and re-run on change.",
)
@click.option(
    "--ignore-disable-overrides",
    is_flag=True,
    default=False,
    help="Print detections even if disabled with // wake-disable-* comments.",
)
@click.option(
    "--ignore-path",
    "ignore_paths",
    multiple=True,
    type=click.Path(),
    help="Detection is not reported if any (sub)detection from a branch is in these paths.",
    envvar="WAKE_DETECT_IGNORE_PATHS",
)
@click.option(
    "--detect-exclude-path",
    "detect_exclude_paths",
    multiple=True,
    type=click.Path(),
    help="Detection is not reported if whole (sub)detections branch is in these paths.",
    envvar="WAKE_DETECT_EXCLUDE_PATHS",
)
@click.option(
    "--exclude",
    "exclude",
    multiple=True,
    type=str,
    help="Exclude detector(s) by name.",
    envvar="WAKE_DETECT_EXCLUDE",
)
@click.option(
    "--only",
    "only",
    multiple=True,
    type=str,
    help="Only run detector(s) by name.",
    envvar="WAKE_DETECT_ONLY",
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
    "--compile-exclude-path",
    "compile_exclude_paths",
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
def run_detect(
    ctx: click.Context,
    no_artifacts: bool,
    ignore_errors: bool,
    export: Optional[str],
    theme: str,
    watch: bool,
    ignore_disable_overrides: bool,
    ignore_paths: Tuple[str],
    detect_exclude_paths: Tuple[str],
    exclude: Tuple[str],
    only: Tuple[str],
    allow_paths: Tuple[str],
    evm_version: Optional[str],
    compile_exclude_paths: Tuple[str],
    include_paths: Tuple[str],
    optimizer_enabled: Optional[bool],
    optimizer_runs: Optional[int],
    remappings: Tuple[str],
    target_version: Optional[str],
    via_ir: Optional[bool],
) -> None:
    """Run vulnerability detectors on the project."""

    if "--help" in ctx.obj["subcommand_args"]:
        return
    if ctx.invoked_subcommand == "list":
        return

    from ..config import WakeConfig

    config = WakeConfig(local_config_path=ctx.obj.get("local_config_path", None))
    config.load_configs()

    compiler_new_options = {}
    detectors_new_options = {}
    deleted_options = []

    if allow_paths:
        compiler_new_options["allow_paths"] = allow_paths
    if evm_version is not None:
        if evm_version == "auto":
            deleted_options.append(("compiler", "solc", "evm_version"))
        else:
            compiler_new_options["evm_version"] = evm_version
    if compile_exclude_paths:
        compiler_new_options["exclude_paths"] = compile_exclude_paths
    if include_paths:
        compiler_new_options["include_paths"] = include_paths
    if optimizer_enabled is not None:
        if "optimizer" not in compiler_new_options:
            compiler_new_options["optimizer"] = {}
        compiler_new_options["optimizer"]["enabled"] = optimizer_enabled
    if optimizer_runs is not None:
        if "optimizer" not in compiler_new_options:
            compiler_new_options["optimizer"] = {}
        compiler_new_options["optimizer"]["runs"] = optimizer_runs
    if remappings:
        compiler_new_options["remappings"] = remappings
    if target_version is not None:
        if target_version == "auto":
            deleted_options.append(("compiler", "solc", "target_version"))
        else:
            compiler_new_options["target_version"] = target_version
    if via_ir is not None:
        compiler_new_options["via_IR"] = via_ir

    if ignore_paths:
        detectors_new_options["ignore_paths"] = ignore_paths
    if detect_exclude_paths:
        detectors_new_options["exclude_paths"] = detect_exclude_paths
    if exclude:
        detectors_new_options["exclude"] = exclude
    if only:
        detectors_new_options["only"] = only

    config.update(
        {
            "compiler": {"solc": compiler_new_options},
            "detectors": detectors_new_options,
        },
        deleted_options,
    )

    asyncio.run(
        detect_(
            config,
            no_artifacts,
            ignore_errors,
            export,
            theme,
            watch,
            ignore_disable_overrides,
        )
    )


# dummy command to allow completion
@run_detect.command(name="all")
@click.pass_context
def run_detect_all(
    ctx: click.Context,
    paths: Tuple[str, ...],
    min_confidence: DetectorConfidence,
    min_impact: DetectorImpact,
) -> None:
    """
    Run all detectors.
    """
    pass


@run_detect.command(name="list")
@click.pass_context
def run_detect_list(ctx):
    """
    List available detectors and their sources.
    """

    def normalize_source(source: Union[str, Path]) -> str:
        if isinstance(source, Path):
            if source == Path.cwd() / "detectors":
                source = "./detectors"
            else:
                try:
                    source = "~/" + str(source.relative_to(Path.home()))
                except ValueError:
                    source = str(source)
        return source

    from rich.table import Table

    from .console import console

    table = Table(title="Available detectors")
    table.add_column("Name")
    table.add_column("Loaded from")
    table.add_column("Available in")

    for detector in sorted(
        run_detect.list_commands(ctx)  # pyright: ignore reportGeneralTypeIssues
    ):
        if detector in {"all", "list"}:
            continue

        table.add_row(
            detector,
            normalize_source(
                run_detect.loaded_from_plugins[  # pyright: ignore reportGeneralTypeIssues
                    detector
                ]
            ),
            ", ".join(
                sorted(
                    normalize_source(s)
                    for s in run_detect.detector_sources.get(  # pyright: ignore reportGeneralTypeIssues
                        detector, []
                    )
                )
            ),
        )

    console.print(table)
