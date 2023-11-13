from __future__ import annotations

from typing import List

import networkx as nx
import rich_click as click

import wake.ir as ir
import wake.ir.types as types
from wake.detectors import (
    Detection,
    DetectionConfidence,
    DetectionImpact,
    Detector,
    DetectorResult,
    detector,
)


# TODO: selfdestruct in Yul
class UnprotectedSelfdestructDetector(Detector):
    _detections: List[DetectorResult]

    def __init__(self):
        self._detections = []

    def detect(self) -> List[DetectorResult]:
        return self._detections

    def visit_function_call(self, node: ir.FunctionCall):
        from wake.analysis.ownable import statement_is_publicly_executable

        if node.function_called not in {
            ir.enums.GlobalSymbol.SELFDESTRUCT,
            ir.enums.GlobalSymbol.SUICIDE,
        }:
            return

        if node.statement is None:
            return

        if statement_is_publicly_executable(node.statement):
            self._detections.append(
                DetectorResult(
                    Detection(node, "Selfdestruct call is not protected"),
                    impact=DetectionImpact.HIGH,
                    confidence=DetectionConfidence.MEDIUM,
                    url="https://ackeeblockchain.com/wake/docs/latest/static-analysis/detectors/unprotected-selfdestruct",
                )
            )

    @detector.command(name="unprotected-selfdestruct")
    def cli(self) -> None:
        """
        Detect selfdestruct calls that may be called by unauthorized parties.
        """
