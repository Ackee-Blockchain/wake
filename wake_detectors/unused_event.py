from __future__ import annotations

from typing import List

import networkx as nx
import rich_click as click

import wake.ir as ir
import wake.ir.types as types
from wake.cli import SolidityName
from wake.detectors import (
    Detection,
    Detector,
    DetectorConfidence,
    DetectorImpact,
    DetectorResult,
    detector,
)
from wake_detectors.utils import generate_detector_uri


class UnusedEventDetector(Detector):
    _detections: List[DetectorResult]

    def __init__(self) -> None:
        self._detections = []

    def detect(self) -> List[DetectorResult]:
        return self._detections

    def visit_event_definition(self, node: ir.EventDefinition):
        if len(node.references) == 0:
            self._detections.append(
                DetectorResult(
                    Detection(
                        node,
                        "Unused event",
                    ),
                    DetectorImpact.INFO,
                    DetectorConfidence.HIGH,
                    uri=generate_detector_uri(
                        name="unused-event",
                        version=self.extra["package_versions"]["eth-wake"],
                    ),
                )
            )

    @detector.command(name="unused-event")
    def cli(self) -> None:
        pass
