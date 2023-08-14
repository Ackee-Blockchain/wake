from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
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


class DetectCli(click.RichGroup):  # pyright: ignore reportPrivateImportUsage
    _plugins_loaded = False
    _plugin_commands: Dict[str, click.Command] = {}

    def __init__(
        self,
        name: Optional[str] = None,
        commands: Optional[
            Union[Dict[str, click.Command], Sequence[click.Command]]
        ] = None,
        **attrs: Any,
    ):
        super().__init__(name=name, commands=commands, **attrs)

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

    def _load_plugins(self) -> None:
        # need to load the module to register detectors
        from woke.detectors import Detector

        if sys.version_info < (3, 10):
            from importlib_metadata import entry_points
        else:
            from importlib.metadata import entry_points

        detector_entry_points = entry_points().select(group="woke.plugins.detectors")
        for entry_point in detector_entry_points:
            entry_point.load()

        if (
            Path.cwd().joinpath("detectors").is_dir()
            and Path.cwd().joinpath("detectors/__init__.py").is_file()
        ):
            from importlib.util import module_from_spec, spec_from_file_location

            sys.path.insert(0, str(Path.cwd()))
            spec = spec_from_file_location("detectors", "detectors/__init__.py")
            if spec is not None and spec.loader is not None:
                module = module_from_spec(spec)
                spec.loader.exec_module(module)

        self._plugins_loaded = True

    def add_command(self, cmd: click.Command, name: Optional[str] = None) -> None:
        self._inject_params(cmd)
        super().add_command(cmd, name)

    def get_command(self, ctx: click.Context, cmd_name: str) -> Optional[click.Command]:
        if not self._plugins_loaded:
            self._load_plugins()
        return self.commands.get(cmd_name)

    def list_commands(self, ctx: click.Context) -> List[str]:
        if not self._plugins_loaded:
            self._load_plugins()
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

    from woke.core.visitor import visit_map
    from woke.detectors.api import DetectionConfidence, DetectionImpact

    from ..compiler import SolcOutputSelectionEnum, SolidityCompiler
    from ..compiler.build_data_model import ProjectBuild
    from ..compiler.solc_frontend import SolcOutputError, SolcOutputErrorSeverityEnum
    from ..config import WokeConfig
    from ..utils import get_class_that_defined_method
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

    detections: List[DetectorResult]
    assert isinstance(ctx.command, DetectCli)
    assert ctx.invoked_subcommand is not None
    command = ctx.command.get_command(ctx, ctx.invoked_subcommand)
    assert command is not None
    assert command.name is not None

    if hasattr(config.detectors, command.name):
        default_map = getattr(config.detectors, command.name)
    else:
        default_map = None

    cls: Type[Detector] = get_class_that_defined_method(
        command.callback
    )  # pyright: ignore reportGeneralTypeIssues
    if cls is not None:

        def _callback(*args, **kwargs):
            instance.paths = [Path(p).resolve() for p in kwargs.pop("paths", [])]

            min_confidence = DetectionConfidence(kwargs.pop("min_confidence", "low"))
            min_impact = DetectionImpact(kwargs.pop("min_impact", "low"))

            original_callback(
                instance, *args, **kwargs
            )  # pyright: ignore reportOptionalCall

            with console.status("[bold green]Running detectors...") as status:
                for path, source_unit in build.source_units.items():
                    if len(instance.paths) == 0 or any(
                        is_relative_to(path, p) for p in instance.paths
                    ):
                        status.update(
                            f"[bold green]Detecting in {source_unit.source_unit_name}..."
                        )
                        for node in source_unit:
                            visit_map[node.ast_node.node_type](instance, node)

            return _filter_detections(
                instance.detect(),
                min_confidence,
                min_impact,
                config,
            )

        instance = cls()
        instance.build = build
        instance.build_info = compiler.latest_build_info
        instance.config = config
        instance.imports_graph = (
            compiler.latest_graph.copy()
        )  # pyright: ignore reportGeneralTypeIssues

        original_callback = command.callback
        command.callback = _callback

        sub_ctx = command.make_context(
            command.name,
            [*ctx.obj["subcommand_protected_args"][1:], *ctx.obj["subcommand_args"]],
            parent=ctx,
            default_map=default_map,
        )
        with sub_ctx:
            detections = sub_ctx.command.invoke(sub_ctx)
    else:

        def _callback(*args, **kwargs):
            click.get_current_context().obj["paths"] = [
                Path(p).resolve() for p in kwargs.pop("paths", [])
            ]
            min_confidence = DetectionConfidence(kwargs.pop("min_confidence", "low"))
            min_impact = DetectionImpact(kwargs.pop("min_impact", "low"))

            return _filter_detections(
                original_callback(
                    *args, **kwargs
                ),  # pyright: ignore reportOptionalCall
                min_confidence,
                min_impact,
                config,
            )

        # this is the case without the Detector class
        args = [*ctx.obj["subcommand_protected_args"][1:], *ctx.obj["subcommand_args"]]
        ctx.obj = {
            "build": build,
            "build_info": compiler.latest_build_info,
            "config": config,
            "imports_graph": compiler.latest_graph.copy(),
        }

        if command.name != "all":
            original_callback = command.callback
            command.callback = _callback

        sub_ctx = command.make_context(
            command.name, args, parent=ctx, default_map=default_map
        )
        with sub_ctx:
            detections = sub_ctx.command.invoke(sub_ctx)

    # TODO order
    for detection in detections:
        _print_detection(ctx.invoked_subcommand, detection, config)

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
    from woke.core.visitor import visit_map
    from woke.utils import get_class_that_defined_method
    from woke.utils.file_utils import is_relative_to

    from .console import console

    build = ctx.obj["build"]
    config = ctx.obj["config"]
    latest_build_info = ctx.obj["build_info"]
    latest_graph = ctx.obj["imports_graph"]

    while not isinstance(ctx.command, DetectCli):
        assert ctx.parent is not None
        ctx = ctx.parent
    assert ctx.parent is not None

    all_detectors = ctx.command.list_commands(ctx)
    if config.detectors.only is None:
        only = set(all_detectors)
    else:
        only = set(config.detectors.only)

    selected_detectors = [
        d
        for d in all_detectors
        if d in only and d not in config.detectors.exclude and d != "all"
    ]
    collected_detectors: Dict[str, Detector] = {}
    detections: Dict[str, Iterable[DetectorResult]] = {}

    # TODO print enabled detectors?

    for detector_name in selected_detectors:
        assert isinstance(ctx.command, DetectCli)
        command = ctx.command.get_command(ctx, detector_name)
        assert command is not None
        assert command.name is not None

        if hasattr(config.detectors, command.name):
            default_map = getattr(config.detectors, command.name)
        else:
            default_map = None

        cls: Type[Detector] = get_class_that_defined_method(
            command.callback
        )  # pyright: ignore reportGeneralTypeIssues
        if cls is not None:

            def _callback(*args, **kwargs):  # pyright: ignore reportGeneralTypeIssues
                kwargs.pop("paths", None)
                kwargs.pop("min_confidence", None)
                kwargs.pop("min_impact", None)

                original_callback(
                    instance, *args, **kwargs
                )  # pyright: ignore reportOptionalCall

            instance = cls()
            instance.build = build
            instance.build_info = latest_build_info
            instance.config = config
            instance.imports_graph = latest_graph.copy()
            instance.paths = [Path(p).resolve() for p in paths]

            original_callback = command.callback
            command.callback = _callback

            sub_ctx = command.make_context(
                command.name,
                [
                    *ctx.parent.obj["subcommand_protected_args"][1:],
                    *ctx.parent.obj["subcommand_args"],
                ],
                parent=ctx,
                default_map=default_map,
            )
            with sub_ctx:
                sub_ctx.command.invoke(sub_ctx)

            collected_detectors[detector_name] = instance
        else:

            def _callback(*args, **kwargs):
                kwargs.pop("paths", None)
                kwargs.pop("min_confidence", None)
                kwargs.pop("min_impact", None)

                return original_callback(
                    *args, **kwargs
                )  # pyright: ignore reportOptionalCall

            # this is the case without the Detector class
            args = [
                *ctx.parent.obj["subcommand_protected_args"][1:],
                *ctx.parent.obj["subcommand_args"],
            ]
            ctx.obj = {
                "build": build,
                "build_info": latest_build_info,
                "config": config,
                "imports_graph": latest_graph.copy(),
                "paths": [Path(p).resolve() for p in paths],
            }

            original_callback = command.callback
            command.callback = _callback

            sub_ctx = command.make_context(
                command.name, args, parent=ctx, default_map=default_map
            )
            with sub_ctx:
                detections[detector_name] = _filter_detections(
                    sub_ctx.command.invoke(sub_ctx), min_confidence, min_impact, config
                )

    with console.status("[bold green]Running detectors...") as status:
        for path, source_unit in build.source_units.items():
            if len(paths) == 0 or any(is_relative_to(path, p) for p in paths):
                status.update(
                    f"[bold green]Detecting in {source_unit.source_unit_name}..."
                )
                for node in source_unit:
                    for detector in collected_detectors.values():
                        visit_map[node.ast_node.node_type](detector, node)

    for detector_name, detector in collected_detectors.items():
        detections[detector_name] = _filter_detections(
            detector.detect(), min_confidence, min_impact, config
        )

    # TODO order
    for detector_name in sorted(detections.keys()):
        for detection in detections[detector_name]:
            _print_detection(detector_name, detection, config)

    if len(detections) == 0:
        console.print("No detections found")
        sys.exit(0)

    sys.exit(1)
