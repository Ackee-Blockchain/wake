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


class UnusedErrorDetector(Detector):
    _detections: List[DetectorResult]

    def __init__(self) -> None:
        self._detections = []

    def detect(self) -> List[DetectorResult]:
        return self._detections

    def visit_error_definition(self, node: ir.ErrorDefinition):
        if len(node.references) == 0:
            self._detections.append(
                DetectorResult(
                    Detection(
                        node,
                        "Unused error",
                    ),
                    DetectorImpact.INFO,
                    DetectorConfidence.HIGH,
                    uri=generate_detector_uri(
                        name="unused-error",
                        version=self.extra["package_versions"]["eth-wake"],
                    ),
                )
            )

    @detector.command(name="unused-error")
    def cli(self) -> None:
        pass
