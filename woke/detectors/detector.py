from __future__ import annotations

from abc import ABCMeta, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional, Tuple

from woke.core.visitor import Visitor
from woke.utils import StrEnum

if TYPE_CHECKING:
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
