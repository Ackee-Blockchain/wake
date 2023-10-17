from __future__ import annotations

import logging
from abc import ABCMeta, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Awaitable,
    Callable,
    Dict,
    List,
    Optional,
    Tuple,
    Type,
    Union,
)

import rich_click as click

from woke.cli.detect import DetectCli, run_detect
from woke.core import get_logger
from woke.core.visitor import Visitor, visit_map
from woke.core.woke_comments import WokeComment, error_commented_out
from woke.utils import StrEnum, get_class_that_defined_method
from woke.utils.file_utils import is_relative_to
from woke.utils.keyed_default_dict import KeyedDefaultDict

if TYPE_CHECKING:
    import networkx as nx
    import rich.console
    from rich.syntax import SyntaxTheme

    from woke.compiler.build_data_model import ProjectBuild, ProjectBuildInfo
    from woke.config import WokeConfig
    from woke.ir import IrAbc, SourceUnit


class DetectionImpact(StrEnum):
    INFO = "info"
    WARNING = "warning"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class DetectionConfidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(eq=True, frozen=True)
class Detection:
    ir_node: IrAbc
    message: str
    subdetections: Tuple[Detection, ...] = field(default_factory=tuple)
    lsp_range: Optional[Tuple[int, int]] = field(default=None)
    subdetections_mandatory: bool = field(default=True)


@dataclass(eq=True, frozen=True)
class DetectorResult:
    detection: Detection
    impact: DetectionImpact
    confidence: DetectionConfidence
    url: Optional[str] = field(default=None)

    def __post_init__(self):
        if self.impact not in DetectionImpact.__members__.values():
            raise ValueError(f"Invalid impact: {self.impact}")
        if self.confidence not in DetectionConfidence.__members__.values():
            raise ValueError(f"Invalid confidence: {self.confidence}")


class Detector(Visitor, metaclass=ABCMeta):
    paths: List[Path]

    @abstractmethod
    def detect(self) -> List[DetectorResult]:
        ...


def _detection_commented_out(
    detector_name: str,
    detection: Detection,
    woke_comments: Dict[str, Dict[int, WokeComment]],
    source_unit: SourceUnit,
) -> bool:
    from woke.ir import DeclarationAbc

    if detection.lsp_range is not None:
        start_line = source_unit.get_line_col_from_byte_offset(detection.lsp_range[0])[
            0
        ]
        end_line = source_unit.get_line_col_from_byte_offset(detection.lsp_range[1])[0]
    elif isinstance(detection.ir_node, DeclarationAbc):
        start_line = source_unit.get_line_col_from_byte_offset(
            detection.ir_node.name_location[0]
        )[0]
        end_line = source_unit.get_line_col_from_byte_offset(
            detection.ir_node.name_location[1]
        )[0]
    else:
        start_line = source_unit.get_line_col_from_byte_offset(
            detection.ir_node.byte_location[0]
        )[0]
        end_line = source_unit.get_line_col_from_byte_offset(
            detection.ir_node.byte_location[1]
        )[0]

    return error_commented_out(
        detector_name,
        start_line,
        end_line,
        woke_comments,
    )


# TODO detection exclude paths
def _filter_detections(
    detector_name: str,
    detections: List[DetectorResult],
    min_confidence: DetectionConfidence,
    min_impact: DetectionImpact,
    config: WokeConfig,
    woke_comments: Dict[Path, Dict[str, Dict[int, WokeComment]]],
    source_units: Dict[Path, SourceUnit],
) -> Tuple[List[DetectorResult], List[DetectorResult]]:
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
    tmp = [
        detection
        for detection in detections
        if confidence_map[detection.confidence] >= confidence_map[min_confidence]
        and impact_map[detection.impact] >= impact_map[min_impact]
        and not _detection_ignored(detection.detection)
    ]
    valid = []
    ignored = []
    for detection in tmp:
        if _detection_commented_out(
            detector_name,
            detection.detection,
            woke_comments[detection.detection.ir_node.file],
            source_units[detection.detection.ir_node.file],
        ):
            ignored.append(detection)
        else:
            valid.append(detection)
    return valid, ignored


def detect(
    detector_names: Union[str, List[str]],
    build: ProjectBuild,
    build_info: ProjectBuildInfo,
    imports_graph: nx.DiGraph,
    config: WokeConfig,
    ctx: Optional[click.Context],
    *,
    paths: Optional[List[Path]] = None,
    args: Optional[List[str]] = None,
    min_confidence: Optional[DetectionConfidence] = None,
    min_impact: Optional[DetectionImpact] = None,
    console: Optional[rich.console.Console] = None,
    verify_paths: bool = True,
    capture_exceptions: bool = False,
    logging_handler: Optional[logging.Handler] = None,
) -> Tuple[
    Dict[str, Tuple[List[DetectorResult], List[DetectorResult]]], Dict[str, Exception]
]:
    from contextlib import nullcontext

    woke_comments: KeyedDefaultDict[
        Path,  # pyright: ignore reportGeneralTypeIssues
        Dict[str, Dict[int, WokeComment]],
    ] = KeyedDefaultDict(
        lambda file: imports_graph.nodes[  # pyright: ignore reportGeneralTypeIssues
            build.source_units[file].source_unit_name
        ]["woke_comments"]
    )

    exceptions = {}

    detectors: List[click.Command] = []
    if isinstance(detector_names, str):
        command = run_detect.get_command(
            ctx,
            detector_names,
            plugin_paths={  # pyright: ignore reportGeneralTypeIssues
                config.project_root_path / "detectors"
            },
            verify_paths=verify_paths,  # pyright: ignore reportGeneralTypeIssues
        )
        try:
            assert command is not None, f"Detector {detector_names} not found"
            detectors.append(command)
        except AssertionError as e:
            if not capture_exceptions:
                raise
            exceptions[detector_names] = e
    elif isinstance(detector_names, list):
        if config.detectors.only is None:
            only = set(detector_names)
        else:
            only = set(config.detectors.only)

        for detector_name in detector_names:
            if (
                detector_name not in only
                or detector_name in config.detectors.exclude
                or detector_name == "all"
            ):
                continue
            command = run_detect.get_command(
                None,
                detector_name,
                plugin_paths={  # pyright: ignore reportGeneralTypeIssues
                    config.project_root_path / "detectors"
                },
                verify_paths=verify_paths,  # pyright: ignore reportGeneralTypeIssues
            )
            try:
                assert command is not None, f"Detector {detector_name} not found"
                detectors.append(command)
            except AssertionError as e:
                if not capture_exceptions:
                    raise
                exceptions[detector_name] = e

    if args is None:
        args = []

    collected_detectors: Dict[str, Detector] = {}
    detections: Dict[str, Tuple[List[DetectorResult], List[DetectorResult]]] = {}

    for command in detectors:
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
                nonlocal paths, min_impact, min_confidence
                if paths is None:
                    paths = [Path(p).resolve() for p in kwargs.pop("paths", [])]
                else:
                    kwargs.pop("paths", None)
                if min_confidence is None:
                    min_confidence = kwargs.pop(
                        "min_confidence", DetectionConfidence.LOW
                    )
                else:
                    kwargs.pop("min_confidence", None)
                if min_impact is None:
                    min_impact = kwargs.pop("min_impact", DetectionImpact.INFO)
                else:
                    kwargs.pop("min_impact", None)

                instance.paths = [Path(p).resolve() for p in paths]
                original_callback(
                    instance, *args, **kwargs
                )  # pyright: ignore reportOptionalCall

            original_callback = command.callback
            command.callback = _callback

            try:
                instance = cls()
                instance.build = build
                instance.build_info = build_info
                instance.config = config
                instance.imports_graph = (
                    imports_graph.copy()
                )  # pyright: ignore reportGeneralTypeIssues
                instance.logger = get_logger(cls.__name__)
                if logging_handler is not None:
                    instance.logger.addHandler(logging_handler)

                sub_ctx = command.make_context(
                    command.name,
                    args,
                    parent=ctx,
                    default_map=default_map,
                )
                with sub_ctx:
                    sub_ctx.command.invoke(sub_ctx)

                collected_detectors[command.name] = instance
            except Exception as e:
                if not capture_exceptions:
                    raise
                exceptions[command.name] = e
            finally:
                command.callback = original_callback
        else:

            def _callback(*args, **kwargs):
                nonlocal paths, min_impact, min_confidence
                if paths is None:
                    paths = [Path(p).resolve() for p in kwargs.pop("paths", [])]
                else:
                    kwargs.pop("paths", None)
                if min_confidence is None:
                    min_confidence = kwargs.pop(
                        "min_confidence", DetectionConfidence.LOW
                    )
                else:
                    kwargs.pop("min_confidence", None)
                if min_impact is None:
                    min_impact = kwargs.pop("min_impact", DetectionImpact.INFO)
                else:
                    kwargs.pop("min_impact", None)

                click.get_current_context().obj["paths"] = [
                    Path(p).resolve() for p in paths
                ]

                return original_callback(
                    *args, **kwargs
                )  # pyright: ignore reportOptionalCall

            original_callback = command.callback
            command.callback = _callback
            assert original_callback is not None

            try:
                sub_ctx = command.make_context(
                    command.name, args, parent=ctx, default_map=default_map
                )
                sub_ctx.obj = {
                    "build": build,
                    "build_info": build_info,
                    "config": config,
                    "imports_graph": imports_graph.copy(),
                    "logger": get_logger(original_callback.__name__),
                }
                if logging_handler is not None:
                    sub_ctx.obj["logger"].addHandler(logging_handler)

                with sub_ctx:
                    detections[command.name] = _filter_detections(
                        command.name,
                        sub_ctx.command.invoke(sub_ctx),
                        min_confidence,  # pyright: ignore reportGeneralTypeIssues
                        min_impact,  # pyright: ignore reportGeneralTypeIssues
                        config,
                        woke_comments,
                        build.source_units,
                    )
            except Exception as e:
                if not capture_exceptions:
                    raise
                exceptions[command.name] = e
            finally:
                command.callback = original_callback

    if paths is None:
        paths = []

    ctx_manager = (
        console.status("[bold green]Running detectors...")
        if console is not None
        else nullcontext()
    )
    with ctx_manager as status:
        for path, source_unit in build.source_units.items():
            if len(paths) == 0 or any(is_relative_to(path, p) for p in paths):
                if status is not None:
                    status.update(
                        f"[bold green]Detecting in {source_unit.source_unit_name}..."
                    )
                for node in source_unit:
                    for detector_name, detector in list(collected_detectors.items()):
                        try:
                            visit_map[node.ast_node.node_type](detector, node)
                        except Exception as e:
                            if not capture_exceptions:
                                raise
                            exceptions[detector_name] = e
                            del collected_detectors[detector_name]

    for detector_name, detector in collected_detectors.items():
        try:
            detections[detector_name] = _filter_detections(
                detector_name,
                detector.detect(),
                min_confidence,  # pyright: ignore reportGeneralTypeIssues
                min_impact,  # pyright: ignore reportGeneralTypeIssues
                config,
                woke_comments,
                build.source_units,
            )
        except Exception as e:
            if not capture_exceptions:
                raise
            exceptions[detector_name] = e

    return detections, exceptions


def print_detection(
    detector_name: str,
    result: DetectorResult,
    config: WokeConfig,
    console: rich.console.Console,
    theme: Union[str, SyntaxTheme] = "monokai",
) -> None:
    from rich.panel import Panel
    from rich.syntax import Syntax
    from rich.tree import Tree

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


async def init_detector(
    config: WokeConfig,
    detector_name: str,
    global_: bool,
    module_name_error_callback: Callable[[str], Awaitable[None]],
    detector_overwrite_callback: Callable[[Path], Awaitable[None]],
    detector_exists_callback: Callable[[str], Awaitable[None]],
) -> Path:
    from .template import TEMPLATE

    assert isinstance(run_detect, DetectCli)

    module_name = detector_name.replace("-", "_")
    if not module_name.isidentifier():
        await module_name_error_callback(module_name)
        # unreachable
        raise ValueError(
            f"Detector name must be a valid Python identifier, got {detector_name}"
        )

    class_name = (
        "".join([s.capitalize() for s in module_name.split("_") if s != ""])
        + "Detector"
    )
    if global_:
        dir_path = config.global_data_path / "global-detectors"
    else:
        dir_path = config.project_root_path / "detectors"
    init_path = dir_path / "__init__.py"
    detector_path = dir_path / f"{module_name}.py"

    if detector_path.exists():
        await detector_overwrite_callback(detector_path)
    else:
        if detector_name in run_detect.loaded_from_plugins:
            if isinstance(run_detect.loaded_from_plugins[detector_name], str):
                other = f"package '{run_detect.loaded_from_plugins[detector_name]}'"
            else:
                other = f"path '{run_detect.loaded_from_plugins[detector_name]}'"
            await detector_exists_callback(other)

    if not dir_path.exists():
        dir_path.mkdir()
        run_detect.add_verified_plugin_path(dir_path)

    detector_path.write_text(
        TEMPLATE.format(class_name=class_name, command_name=detector_name)
    )

    if not init_path.exists():
        init_path.touch()

    import_str = f"from .{module_name} import {class_name}"
    if import_str not in init_path.read_text().splitlines():
        with init_path.open("a") as f:
            f.write(f"\n{import_str}")

    return detector_path
