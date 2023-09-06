from __future__ import annotations

from abc import ABCMeta, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple, Type, Union

import rich_click as click

from woke.cli.detect import run_detect
from woke.core.visitor import Visitor, visit_map
from woke.utils import StrEnum, get_class_that_defined_method
from woke.utils.file_utils import is_relative_to

if TYPE_CHECKING:
    import networkx as nx
    import rich.console

    from woke.compiler.build_data_model import ProjectBuild, ProjectBuildInfo
    from woke.config import WokeConfig
    from woke.ir.abc import IrAbc


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


# TODO detection exclude paths
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


def detect(
    detector_names: Union[str, List[str]],
    build: ProjectBuild,
    build_info: ProjectBuildInfo,
    imports_graph: nx.DiGraph,
    config: WokeConfig,
    ctx: Optional[click.Context],
    paths: Optional[List[Path]] = None,
    args: Optional[List[str]] = None,
    min_confidence: Optional[DetectionConfidence] = None,
    min_impact: Optional[DetectionImpact] = None,
    console: Optional[rich.console.Console] = None,
) -> Dict[str, List[DetectorResult]]:
    from contextlib import nullcontext

    detectors: List[click.Command] = []
    if isinstance(detector_names, str):
        detectors = [
            run_detect.get_command(
                ctx,
                detector_names,
                plugin_paths={  # pyright: ignore reportGeneralTypeIssues
                    config.project_root_path / "detectors"
                },
            )
        ]
    elif isinstance(detector_names, list):
        if config.detectors.only is None:
            only = set(detector_names)
        else:
            only = set(config.detectors.only)

        detectors = [
            run_detect.get_command(
                None,
                d,
                plugin_paths={  # pyright: ignore reportGeneralTypeIssues
                    config.project_root_path / "detectors"
                },
            )
            for d in detector_names
            if d in only and d not in config.detectors.exclude and d != "all"
        ]

    if args is None:
        args = []

    collected_detectors: Dict[str, Detector] = {}
    detections: Dict[str, List[DetectorResult]] = {}

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

            instance = cls()
            instance.build = build
            instance.build_info = build_info
            instance.config = config
            instance.imports_graph = (
                imports_graph.copy()
            )  # pyright: ignore reportGeneralTypeIssues

            original_callback = command.callback
            command.callback = _callback

            sub_ctx = command.make_context(
                command.name,
                args,
                parent=ctx,
                default_map=default_map,
            )
            with sub_ctx:
                sub_ctx.command.invoke(sub_ctx)

            command.callback = original_callback

            collected_detectors[command.name] = instance
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

            sub_ctx = command.make_context(
                command.name, args, parent=ctx, default_map=default_map
            )
            sub_ctx.obj = {
                "build": build,
                "build_info": build_info,
                "config": config,
                "imports_graph": imports_graph.copy(),
            }

            original_callback = command.callback
            command.callback = _callback

            with sub_ctx:
                detections[command.name] = _filter_detections(
                    sub_ctx.command.invoke(sub_ctx),
                    min_confidence,  # pyright: ignore reportGeneralTypeIssues
                    min_impact,  # pyright: ignore reportGeneralTypeIssues
                    config,
                )

            command.callback = original_callback

    ctx_manager = (
        console.status("[bold green]Running detectors...")
        if console is not None
        else nullcontext()
    )
    assert paths is not None
    with ctx_manager as status:
        for path, source_unit in build.source_units.items():
            if len(paths) == 0 or any(is_relative_to(path, p) for p in paths):
                if status is not None:
                    status.update(
                        f"[bold green]Detecting in {source_unit.source_unit_name}..."
                    )
                for node in source_unit:
                    for detector in collected_detectors.values():
                        visit_map[node.ast_node.node_type](detector, node)

    for detector_name, detector in collected_detectors.items():
        detections[detector_name] = _filter_detections(
            detector.detect(),
            min_confidence,  # pyright: ignore reportGeneralTypeIssues
            min_impact,  # pyright: ignore reportGeneralTypeIssues
            config,
        )

    return detections
