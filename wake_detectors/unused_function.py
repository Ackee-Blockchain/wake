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


class UnusedFunctionDetector(Detector):
    _detections: List[DetectorResult]

    def __init__(self) -> None:
        self._detections = []

    def detect(self) -> List[DetectorResult]:
        return self._detections

    def visit_function_definition(self, node: ir.FunctionDefinition):
        from wake.analysis.utils import get_all_base_and_child_declarations

        if node.visibility in {
            ir.enums.Visibility.PUBLIC,
            ir.enums.Visibility.EXTERNAL,
        } or node.kind not in {
            ir.enums.FunctionKind.FUNCTION,
            ir.enums.FunctionKind.FREE_FUNCTION,
        }:
            return

        if all(
            len(d.references) == 0 for d in get_all_base_and_child_declarations(node)
        ):
            self._detections.append(
                DetectorResult(
                    Detection(
                        node,
                        "Unused function",
                    ),
                    impact=DetectorImpact.INFO,
                    confidence=DetectorConfidence.HIGH,
                    uri=generate_detector_uri(
                        name="unused-function",
                        version=self.extra["package_versions"]["eth-wake"],
                    ),
                )
            )

    @detector.command(name="unused-function")
    def cli(self) -> None:
        """
        Unused function
        """
