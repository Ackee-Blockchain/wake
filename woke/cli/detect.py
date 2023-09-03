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

if TYPE_CHECKING:
    from rich.syntax import SyntaxTheme

    from woke.config import WokeConfig
    from woke.detectors import (
        Detection,
        DetectionConfidence,
        DetectionImpact,
        Detector,
        DetectorResult,
    )

logger = logging.getLogger(__name__)


class DetectCli(click.RichGroup):  # pyright: ignore reportPrivateImportUsage
    _plugin_paths: AbstractSet[Path] = set()
    _plugin_commands: Dict[str, click.Command] = {}
    _failed_plugin_paths: Set[Tuple[Path, Exception]] = set()
    _failed_plugin_entry_points: Set[Tuple[str, Exception]] = set()
    _completion_mode: bool
    _global_data_path: Path

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

        self._completion_mode = "_WOKE_COMPLETE" in os.environ

        system = platform.system()
        try:
            self._global_data_path = Path(os.environ["XDG_DATA_HOME"]) / "woke"
        except KeyError:
            if system in {"Linux", "Darwin"}:
                self._global_data_path = Path.home() / ".local" / "share" / "woke"
            elif system == "Windows":
                self._global_data_path = Path(os.environ["LOCALAPPDATA"]) / "woke"
            else:
                raise RuntimeError(f"Unsupported system: {system}")

        for command in self.commands.values():
            self._inject_params(command)

    @staticmethod
    def _inject_params(command: click.Command) -> None:
        command.params.append(
            click.Argument(
                ["paths"],
                nargs=-1,  # TODO: leave this as nargs=-1? other nargs=-1 are not possible
                type=click.Path(exists=True),
            )
        )
        command.params.append(
            click.Option(
                ["--min-impact"],
                type=click.Choice(["info", "warning", "low", "medium", "high"]),
                default="info",
                help="Minimum impact level to report",
            )
        )
        command.params.append(
            click.Option(
                ["--min-confidence"],
                type=click.Choice(["low", "medium", "high"]),
                default="low",
                help="Minimum confidence level to report",
            )
        )

    @property
    def failed_plugin_paths(self) -> FrozenSet[Tuple[Path, Exception]]:
        return frozenset(self._failed_plugin_paths)

    @property
    def failed_plugin_entry_points(self) -> FrozenSet[Tuple[str, Exception]]:
        return frozenset(self._failed_plugin_entry_points)

    def _verify_plugin_path(self, path: Path) -> bool:
        import pickle

        from rich.prompt import Confirm

        try:
            data: Set[Path] = pickle.loads(
                self._global_data_path.joinpath("verified_detectors.bin").read_bytes()
            )
        except FileNotFoundError:
            data = set()
        if path not in data:
            if self._completion_mode:
                return False

            verified = Confirm.ask(f"Do you trust detectors in {path}?", default=False)
            if verified:
                data.add(path)
                self._global_data_path.joinpath("verified_detectors.bin").write_bytes(
                    pickle.dumps(data)
                )
            return verified
        return True

    def _load_plugins(self, plugin_paths: AbstractSet[Path]) -> None:
        # need to load the module to register detectors
        from woke.detectors import Detector

        if sys.version_info < (3, 10):
            from importlib_metadata import entry_points
        else:
            from importlib.metadata import entry_points
        from importlib.util import module_from_spec, spec_from_file_location

        detector_entry_points = entry_points().select(group="woke.plugins.detectors")
        for entry_point in detector_entry_points:
            try:
                entry_point.load()
            except Exception as e:
                self._failed_plugin_entry_points.add((entry_point.value, e))
                if not self._completion_mode:
                    logger.warning(
                        f"Failed to load detectors from package '{entry_point.value}': {e}"
                    )

        for path in plugin_paths:
            if not path.exists() or not self._verify_plugin_path(path):
                continue
            sys.path.insert(0, str(path.parent))
            try:
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
                    logger.warning(f"Failed to load detectors from path {path}: {e}")

        self._plugin_paths = plugin_paths

    def add_command(self, cmd: click.Command, name: Optional[str] = None) -> None:
        self._inject_params(cmd)
        super().add_command(cmd, name)

    def get_command(
        self,
        ctx: click.Context,
        cmd_name: str,
        plugin_paths: AbstractSet[Path] = frozenset([Path.cwd() / "detectors"]),
    ) -> Optional[click.Command]:
        if plugin_paths != self._plugin_paths:
            self._load_plugins(plugin_paths)
        return self.commands.get(cmd_name)

    def list_commands(
        self,
        ctx: click.Context,
        plugin_paths: AbstractSet[Path] = frozenset([Path.cwd() / "detectors"]),
    ) -> List[str]:
        if plugin_paths != self._plugin_paths:
            self._load_plugins(plugin_paths)
        return sorted(self.commands)

    def invoke(self, ctx: click.Context):
        ctx.obj["subcommand_args"] = ctx.args
        ctx.obj["subcommand_protected_args"] = ctx.protected_args
        super().invoke(ctx)


def _print_detection(
    detector_name: str,
    result: DetectorResult,
    config: WokeConfig,
    theme: Union[str, SyntaxTheme] = "monokai",
) -> None:
    from rich.panel import Panel
    from rich.syntax import Syntax
    from rich.tree import Tree

    from woke.detectors.api import Detection, DetectorResult

    from .console import console

    def print_result(
        info: Union[DetectorResult, Detection],
        tree: Optional[Tree],
        detector_id: Optional[str],
    ) -> Tree:
        if isinstance(info, DetectorResult):
            detection = info.detection
        else:
            detection = info

        source_unit = detection.ir_node.source_unit
        line, col = source_unit.get_line_col_from_byte_offset(
            detection.ir_node.byte_location[0]
        )
        assert source_unit._lines_index is not None
        line -= 1
        source = ""
        start_line_index = max(0, line - 3)
        end_line_index = min(len(source_unit._lines_index), line + 3)
        for i in range(start_line_index, end_line_index):
            source += source_unit._lines_index[i][0].decode("utf-8")

        link = config.general.link_format.format(
            path=source_unit.file,
            line=line + 1,
            col=col,
        )
        subtitle = f"[link={link}]{source_unit.source_unit_name}[/link]"

        title = ""
        if isinstance(info, DetectorResult):
            if info.impact == "info":
                title += "[[bold blue]INFO[/bold blue]] "
            elif info.impact == "warning":
                title += "[[bold yellow]WARNING[/bold yellow]] "
            elif info.impact == "low":
                title += "[[bold cyan]LOW[/bold cyan]] "
            elif info.impact == "medium":
                title += "[[bold magenta]MEDIUM[/bold magenta]] "
            elif info.impact == "high":
                title += "[[bold red]HIGH[/bold red]] "

        title += detection.message
        if detector_id is not None:
            title += f" \[{detector_id}]"  # pyright: ignore reportInvalidStringEscapeSequence

        panel = Panel.fit(
            Syntax(
                source,
                "solidity",
                theme=theme,
                line_numbers=True,
                start_line=start_line_index + 1,
                highlight_lines={line + 1},
            ),
            title=title,
            title_align="left",
            subtitle=subtitle,
            subtitle_align="left",
        )

        if tree is None:
            t = Tree(panel)
        else:
            t = tree.add(panel)

        for subdetection in detection.subdetections:
            print_result(subdetection, t, None)

        return t

    console.print("\n")
    tree = print_result(result, None, detector_name)
    console.print(tree)


def _filter_detections(
    detections: List[DetectorResult],
    min_confidence: DetectionConfidence,
    min_impact: DetectionImpact,
    config: WokeConfig,
) -> List[DetectorResult]:
    from woke.utils.file_utils import is_relative_to

    def _detection_ignored(detection: Detection) -> bool:
        return any(
            is_relative_to(detection.ir_node.file, p)
            for p in config.detectors.ignore_paths
        ) and all(_detection_ignored(d) for d in detection.subdetections)

    confidence_map = {
        "low": 0,
        "medium": 1,
        "high": 2,
    }
    impact_map = {
        "info": 0,
        "warning": 1,
        "low": 2,
        "medium": 3,
        "high": 4,
    }
    return [
        detection
        for detection in detections
        if confidence_map[detection.confidence] >= confidence_map[min_confidence]
        and impact_map[detection.impact] >= impact_map[min_impact]
        and not _detection_ignored(detection.detection)
    ]


@click.group(
    name="detect",
    cls=DetectCli,
    context_settings={"auto_envvar_prefix": "WOKE_DETECTOR"},
)
@click.option(
    "--no-artifacts", is_flag=True, default=False, help="Do not write build artifacts."
)
@click.pass_context
def run_detect(ctx: click.Context, no_artifacts: bool) -> None:
    """Run vulnerability detectors on the project."""

    if "--help" in ctx.obj["subcommand_args"]:
        return

    from ..compiler import SolcOutputSelectionEnum, SolidityCompiler
    from ..compiler.build_data_model import ProjectBuild
    from ..compiler.solc_frontend import SolcOutputError, SolcOutputErrorSeverityEnum
    from ..config import WokeConfig
    from ..utils.file_utils import is_relative_to
    from .console import console

    config = WokeConfig()
    config.load_configs()  # load ~/.woke/config.toml and ./woke.toml

    sol_files: Set[Path] = set()
    start = time.perf_counter()
    with console.status("[bold green]Searching for *.sol files...[/]"):
        for file in config.project_root_path.rglob("**/*.sol"):
            if (
                not any(
                    is_relative_to(file, p) for p in config.compiler.solc.ignore_paths
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

    build: ProjectBuild
    errors: Set[SolcOutputError]
    build, errors = asyncio.run(
        compiler.compile(
            sol_files,
            [SolcOutputSelectionEnum.ALL],
            write_artifacts=not no_artifacts,
            console=console,
            no_warnings=True,
        )
    )

    errored = any(
        error.severity == SolcOutputErrorSeverityEnum.ERROR for error in errors
    )
    if errored:
        sys.exit(1)

    assert compiler.latest_build_info is not None
    assert compiler.latest_graph is not None

    from woke.detectors.api import detect

    assert ctx.invoked_subcommand is not None
    if ctx.invoked_subcommand == "all":
        ctx.obj = {
            "build": build,
            "build_info": compiler.latest_build_info,
            "config": config,
            "imports_graph": compiler.latest_graph,
        }
    else:
        detections = detect(
            ctx.invoked_subcommand,
            build,
            compiler.latest_build_info,
            compiler.latest_graph,
            config,
            ctx,
            ctx.obj["subcommand_args"],
            console=console,
        )

        # TODO order
        for detector_name in sorted(detections.keys()):
            for detection in detections[detector_name]:
                _print_detection(detector_name, detection, config)

        if len(detections) == 0:
            console.print("No detections found")
            sys.exit(0)

        sys.exit(1)


@run_detect.command(name="all")
@click.pass_context
def run_detect_all(
    ctx: click.Context,
    paths: Tuple[str, ...],
    min_confidence: DetectionConfidence,
    min_impact: DetectionImpact,
) -> None:
    """
    Run all detectors.
    """
    from woke.detectors.api import detect

    from .console import console

    build = ctx.obj["build"]
    config = ctx.obj["config"]
    latest_build_info = ctx.obj["build_info"]
    latest_graph = ctx.obj["imports_graph"]

    detections = detect(
        run_detect.list_commands(ctx),
        build,
        latest_build_info,
        latest_graph,
        config,
        ctx,
        paths=[Path(p).resolve() for p in paths],
        min_confidence=min_confidence,
        min_impact=min_impact,
        console=console,
    )

    # TODO order
    for detector_name in sorted(detections.keys()):
        for detection in detections[detector_name]:
            _print_detection(detector_name, detection, config)

    if len(detections) == 0:
        console.print("No detections found")
        sys.exit(0)

    sys.exit(1)
