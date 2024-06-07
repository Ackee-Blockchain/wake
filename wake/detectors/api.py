from __future__ import annotations

import logging
from abc import ABCMeta, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from functools import partial, total_ordering
from itertools import chain
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Awaitable,
    Callable,
    DefaultDict,
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

from wake.cli.detect import DetectCli, run_detect
from wake.core import get_logger
from wake.core.visitor import Visitor, group_map, visit_map
from wake.core.wake_comments import WakeComment, error_commented_out
from wake.utils import StrEnum, get_class_that_defined_method
from wake.utils.file_utils import is_relative_to, wake_contracts_path
from wake.utils.keyed_default_dict import KeyedDefaultDict

if TYPE_CHECKING:
    import threading

    import networkx as nx
    import rich.console
    from rich.syntax import SyntaxTheme

    from wake.compiler.build_data_model import ProjectBuild, ProjectBuildInfo
    from wake.config import WakeConfig
    from wake.core.lsp_provider import LspProvider
    from wake.ir import IrAbc, SourceUnit


@total_ordering
class DetectorImpact(StrEnum):
    """
    The impact of a [DetectorResult][wake.detectors.api.DetectorResult].
    """

    INFO = "info"
    WARNING = "warning"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

    def __lt__(self, other: Any) -> bool:
        if not isinstance(other, DetectorImpact):
            return NotImplemented
        prio = ["info", "warning", "low", "medium", "high"]
        return prio.index(self.value) < prio.index(other.value)


@total_ordering
class DetectorConfidence(StrEnum):
    """
    The confidence of a [DetectorResult][wake.detectors.api.DetectorResult].
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

    def __lt__(self, other: Any) -> bool:
        if not isinstance(other, DetectorConfidence):
            return NotImplemented
        prio = ["low", "medium", "high"]
        return prio.index(self.value) < prio.index(other.value)


@dataclass(eq=True, frozen=True)
class Detection:
    """
    A single detection bound to a location in the source code through an IR node. May contain any number of subdetections.

    Attributes:
        ir_node: IR node representing the detection.
        message: User-friendly message describing the detection.
        subdetections: Subdetections of this detection.
        lsp_range: Byte offsets (start, end) of the detection used for highlighting in LSP diagnostics and in SARIF export.
        subdetections_mandatory: Whether the detection requires at least one subdetection to be valid,
            or if the subdetections are not mandatory for the existence of the detection.
            This attribute determines whether the detection should be filtered out if all subdetections are filtered out based on the detectors [ignore_paths][wake.config.data_model.DetectorsConfig.ignore_paths] configuration.
    """

    ir_node: IrAbc
    message: str
    subdetections: Tuple[Detection, ...] = field(default_factory=tuple)
    lsp_range: Optional[Tuple[int, int]] = field(default=None)
    subdetections_mandatory: bool = field(default=True)


@dataclass(eq=True, frozen=True)
class DetectorResult:
    """
    A single result reported by a [Detector][wake.detectors.api.Detector].

    Attributes:
        detection: Detection describing the location in the source code and the message.
        impact: Impact of the detection.
        confidence: Confidence of the detection.
        uri: Optional URI to a page describing the detection.
    """

    detection: Detection
    impact: DetectorImpact
    confidence: DetectorConfidence
    uri: Optional[str] = field(default=None)

    def __post_init__(self):
        if self.impact not in DetectorImpact.__members__.values():
            raise ValueError(f"Invalid impact: {self.impact}")
        if self.confidence not in DetectorConfidence.__members__.values():
            raise ValueError(f"Invalid confidence: {self.confidence}")


class Detector(Visitor, metaclass=ABCMeta):
    """
    Base class for detectors.

    Attributes:
        paths: Paths the detector should operate on. May be empty if a user did not specify any paths, e.g. when running `wake detect all`.
            In this case, the detector should operate on all paths. May be ignored unless [visit_mode][wake.detectors.api.Detector.visit_mode] is `all`.
        extra: Extra data shared between all detectors in a single run. May contain additional data set by the execution engine.
    """

    paths: List[Path]
    extra: Dict[Any, Any]
    lsp_provider: Optional[LspProvider]
    execution_mode: Literal["cli", "lsp", "both"] = "both"  # TODO is this needed?

    @property
    def visit_mode(self) -> Literal["paths", "all"]:
        """
        Configurable visit mode of the detector. If set to `paths`, the detector `visit_` methods will be called only for the paths specified by the user.
        If set to `all`, the detector `visit_` methods will be called for all paths, leaving the filtering of detections to the detector implementation.
        In this case, the detector should use the `paths` attribute to determine which paths to operate on.

        Returns:
            Visit mode of the detector.
        """
        return "paths"

    @abstractmethod
    def detect(self) -> List[DetectorResult]:
        """
        Abstract method that must be implemented in a detector to return the discovered detections.

        Returns:
            List of detector results.
        """
        ...


def _detection_commented_out(
    detector_name: str,
    detection: Detection,
    wake_comments: Dict[str, Dict[int, WakeComment]],
    source_unit: SourceUnit,
) -> bool:
    from wake.ir import DeclarationAbc

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

    # returned line numbers are 1-based, but wake_comments are 0-based
    start_line -= 1
    end_line -= 1

    return error_commented_out(
        detector_name,
        start_line,
        end_line,
        wake_comments,
    )


def _strip_excluded_subdetections(
    detection: Detection, config: WakeConfig
) -> Detection:
    """
    Strip all subdetections that are located in excluded paths and their parents are also in excluded paths.
    In other words, remove all subdetection branches that whole end up in excluded paths.
    """
    if len(detection.subdetections) == 0:
        return detection

    subdetections = []
    for d in detection.subdetections:
        if not any(
            is_relative_to(d.ir_node.source_unit.file, p)
            for p in chain(config.detectors.exclude_paths, [wake_contracts_path])
        ):
            subdetections.append(d)
            continue

        d = _strip_excluded_subdetections(d, config)
        if len(d.subdetections) != 0:
            subdetections.append(d)

    return Detection(
        detection.ir_node,
        detection.message,
        tuple(subdetections),
        detection.lsp_range,
        detection.subdetections_mandatory,
    )


def _strip_ignored_subdetections(detection: Detection, config: WakeConfig) -> Detection:
    """
    Strip all subdetections that are located in ignored paths.
    """
    if len(detection.subdetections) == 0:
        return detection

    subdetections = []
    for d in detection.subdetections:
        if any(
            is_relative_to(d.ir_node.source_unit.file, p)
            for p in config.detectors.ignore_paths
        ):
            continue

        l = len(d.subdetections)
        if l == 0:
            subdetections.append(d)
            continue
        d = _strip_ignored_subdetections(d, config)
        if len(d.subdetections) == 0 and l > 0 and d.subdetections_mandatory:
            continue
        subdetections.append(d)

    return Detection(
        detection.ir_node,
        detection.message,
        tuple(subdetections),
        detection.lsp_range,
        detection.subdetections_mandatory,
    )


def _filter_detections(
    detector_name: str,
    detections: List[DetectorResult],
    min_impact: DetectorImpact,
    min_confidence: DetectorConfidence,
    config: WakeConfig,
    wake_comments: Dict[Path, Dict[str, Dict[int, WakeComment]]],
    source_units: Dict[Path, SourceUnit],
) -> Tuple[List[DetectorResult], List[DetectorResult]]:
    from wake.utils.file_utils import is_relative_to

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
    ]
    valid = []
    ignored = []
    for detection in tmp:
        if any(
            is_relative_to(detection.detection.ir_node.source_unit.file, p)
            for p in config.detectors.ignore_paths
        ):
            continue

        l = len(detection.detection.subdetections)
        detection = DetectorResult(
            _strip_ignored_subdetections(detection.detection, config),
            detection.impact,
            detection.confidence,
            detection.uri,
        )
        if (
            len(detection.detection.subdetections) == 0
            and l > 0
            and detection.detection.subdetections_mandatory
        ):
            continue

        if any(
            is_relative_to(detection.detection.ir_node.source_unit.file, p)
            for p in chain(config.detectors.exclude_paths, [wake_contracts_path])
        ):
            detection = DetectorResult(
                _strip_excluded_subdetections(detection.detection, config),
                detection.impact,
                detection.confidence,
                detection.uri,
            )
            if len(detection.detection.subdetections) == 0:
                continue

        if _detection_commented_out(
            detector_name,
            detection.detection,
            wake_comments[detection.detection.ir_node.source_unit.file],
            source_units[detection.detection.ir_node.source_unit.file],
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
    config: WakeConfig,
    ctx: Optional[click.Context],
    lsp_provider: Optional[LspProvider],
    *,
    paths: Optional[List[Path]] = None,
    args: Optional[List[str]] = None,
    default_min_impact: DetectorImpact = DetectorImpact.INFO,
    default_min_confidence: DetectorConfidence = DetectorConfidence.LOW,
    console: Optional[rich.console.Console] = None,
    verify_paths: bool = True,
    capture_exceptions: bool = False,
    logging_handler: Optional[logging.Handler] = None,
    extra: Optional[Dict[Any, Any]] = None,
    cancel_event: Optional[threading.Event] = None,
) -> Tuple[
    List[click.Command],
    Dict[str, Tuple[List[DetectorResult], List[DetectorResult]]],
    Dict[str, Exception],
]:
    from contextlib import nullcontext

    from wake.core.exceptions import ThreadCancelledError
    from wake.utils import get_package_version

    if extra is None:
        extra = {}
    if "package_versions" not in extra:
        extra["package_versions"] = {}
    extra["package_versions"]["eth-wake"] = get_package_version("eth-wake")

    wake_comments: KeyedDefaultDict[
        Path,  # pyright: ignore reportGeneralTypeIssues
        Dict[str, Dict[int, WakeComment]],
    ] = KeyedDefaultDict(
        lambda file: imports_graph.nodes[  # pyright: ignore reportGeneralTypeIssues
            build.source_units[file].source_unit_name
        ]["wake_comments"]
    )

    exceptions = {}

    detectors: List[click.Command] = []
    if isinstance(detector_names, str):
        command = run_detect.get_command(
            ctx,  # pyright: ignore reportGeneralTypeIssues
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
                or detector_name in {"all", "list"}
            ):
                continue
            command = run_detect.get_command(
                None,  # pyright: ignore reportGeneralTypeIssues
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
    visit_all_detectors: Set[str] = set()
    detections: Dict[str, Tuple[List[DetectorResult], List[DetectorResult]]] = {}
    min_confidence_by_detector: DefaultDict[str, DetectorConfidence] = defaultdict(
        lambda: default_min_confidence
    )
    min_impact_by_detector: DefaultDict[str, DetectorImpact] = defaultdict(
        lambda: default_min_impact
    )

    for command in list(detectors):
        if cancel_event is not None and cancel_event.is_set():
            raise ThreadCancelledError()

        assert command is not None
        assert command.name is not None

        if lsp_provider is not None:
            lsp_provider._current_sort_tag = command.name

        if hasattr(config.detector, command.name):
            default_map = getattr(config.detector, command.name)
        else:
            default_map = None

        cls: Type[Detector] = get_class_that_defined_method(
            command.callback
        )  # pyright: ignore reportGeneralTypeIssues
        if cls is not None:

            def _callback(  # pyright: ignore reportGeneralTypeIssues
                detector_name: str, *args, **kwargs
            ):
                nonlocal paths, min_impact_by_detector, min_confidence_by_detector
                if paths is None:
                    paths = [Path(p).resolve() for p in kwargs.pop("paths", [])]
                else:
                    kwargs.pop("paths", None)

                min_impact_by_detector[detector_name] = kwargs.pop(
                    "min_impact", default_min_impact
                )
                min_confidence_by_detector[detector_name] = kwargs.pop(
                    "min_confidence", default_min_confidence
                )

                instance.paths = [Path(p).resolve() for p in paths]
                original_callback(
                    instance, *args, **kwargs
                )  # pyright: ignore reportOptionalCall

            original_callback = command.callback
            command.callback = partial(_callback, command.name)

            if lsp_provider is not None and cls.execution_mode == "cli":
                detectors.remove(command)
                continue
            elif lsp_provider is None and cls.execution_mode == "lsp":
                detectors.remove(command)
                continue

            try:
                instance = object.__new__(cls)
                instance.build = build
                instance.build_info = build_info
                instance.config = config
                instance.extra = extra
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

                    collected_detectors[command.name] = instance
                    if instance.visit_mode == "all":
                        visit_all_detectors.add(command.name)
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
                detectors.remove(command)
                continue

            def _callback(detector_name: str, *args, **kwargs):
                nonlocal paths, min_impact_by_detector, min_confidence_by_detector
                if paths is None:
                    paths = [Path(p).resolve() for p in kwargs.pop("paths", [])]
                else:
                    kwargs.pop("paths", None)

                min_impact_by_detector[detector_name] = kwargs.pop(
                    "min_impact", default_min_impact
                )
                min_confidence_by_detector[detector_name] = kwargs.pop(
                    "min_confidence", default_min_confidence
                )

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
                    # no need to set lsp_provider as legacy detectors are not executed by the LSP server
                }
                if logging_handler is not None:
                    sub_ctx.obj[
                        "logger"
                    ].addHandler(  # pyright: ignore reportGeneralTypeIssues
                        logging_handler
                    )

                try:
                    with sub_ctx:
                        d = sub_ctx.command.invoke(sub_ctx)
                        detections[command.name] = _filter_detections(
                            command.name,
                            d,
                            min_impact_by_detector[command.name],
                            min_confidence_by_detector[command.name],
                            config,
                            wake_comments,
                            build.source_units,
                        )
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

    ctx_manager = (
        console.status("[bold green]Running detectors...")
        if console is not None and (ctx is None or not ctx.obj.get("debug", False))
        else nullcontext()
    )
    with ctx_manager as status:
        for path, source_unit in build.source_units.items():
            if cancel_event is not None and cancel_event.is_set():
                raise ThreadCancelledError()

            if any(is_relative_to(path, p) for p in config.detectors.ignore_paths):
                continue

            target_detectors = visit_all_detectors
            if len(paths) == 0 or any(is_relative_to(path, p) for p in paths):
                target_detectors = collected_detectors.keys()
                if status is not None:
                    status.update(
                        f"[bold green]Detecting in {source_unit.source_unit_name}..."
                    )

            if len(target_detectors) == 0:
                continue

            for node in source_unit:
                for detector_name in list(target_detectors):
                    if lsp_provider is not None:
                        lsp_provider._current_sort_tag = detector_name

                    detector = collected_detectors[detector_name]
                    try:
                        detector.visit_ir_abc(node)
                        if node.ast_node.node_type in group_map:
                            for group in group_map[node.ast_node.node_type]:
                                visit_map[group](detector, node)
                        visit_map[node.ast_node.node_type](detector, node)
                    except Exception as e:
                        if not capture_exceptions:
                            raise
                        exceptions[detector_name] = e
                        if logging_handler is not None:
                            detector.logger.removeHandler(logging_handler)
                        del collected_detectors[detector_name]

    for detector_name, detector in collected_detectors.items():
        if cancel_event is not None and cancel_event.is_set():
            raise ThreadCancelledError()

        if lsp_provider is not None:
            lsp_provider._current_sort_tag = detector_name

        try:
            detections[detector_name] = _filter_detections(
                detector_name,
                detector.detect(),
                min_impact_by_detector[detector_name],
                min_confidence_by_detector[detector_name],
                config,
                wake_comments,
                build.source_units,
            )
        except Exception as e:
            if not capture_exceptions:
                raise
            exceptions[detector_name] = e
        finally:
            if logging_handler is not None:
                detector.logger.removeHandler(logging_handler)

    return detectors, detections, exceptions


def print_detection(
    detector_name: str,
    result: DetectorResult,
    config: WakeConfig,
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
                title += "[[bold blue]INFO[/bold blue]]"
            elif info.impact == "warning":
                title += "[[bold yellow]WARNING[/bold yellow]]"
            elif info.impact == "low":
                title += "[[bold cyan]LOW[/bold cyan]]"
            elif info.impact == "medium":
                title += "[[bold magenta]MEDIUM[/bold magenta]]"
            elif info.impact == "high":
                title += "[[bold red]HIGH[/bold red]]"

            if info.confidence == "low":
                title += "[[bold cyan]LOW[/bold cyan]]"
            elif info.confidence == "medium":
                title += "[[bold magenta]MEDIUM[/bold magenta]]"
            elif info.confidence == "high":
                title += "[[bold red]HIGH[/bold red]]"
            title += " "

        title += detection.message
        if detector_id is not None:
            if isinstance(info, DetectorResult) and info.uri is not None:
                title += f" [link={info.uri}]\[{detector_id}][/link]"  # pyright: ignore reportInvalidStringEscapeSequence
            else:
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
    config: WakeConfig,
    detector_name: str,
    global_: bool,
    module_name_error_callback: Callable[[str], Awaitable[None]],
    detector_overwrite_callback: Callable[[Path], Awaitable[None]],
    detector_exists_callback: Callable[[str], Awaitable[None]],
    *,
    path: Optional[Path] = None,
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
    if path is not None:
        dir_path = path
    elif global_:
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
    init_text = init_path.read_text()
    if import_str not in init_text.splitlines():
        with init_path.open("a") as f:
            lines = init_text.splitlines(keepends=True)
            if len(lines) != 0 and not lines[-1].endswith("\n"):
                f.write("\n")
            f.write(f"{import_str}\n")

    return detector_path
