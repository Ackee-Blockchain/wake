from __future__ import annotations

import logging
from typing import List, Set

import woke.ir as ir
from woke.detectors import (
    Detection,
    DetectionConfidence,
    DetectionImpact,
    Detector,
    DetectorResult,
    detector,
)

logger = logging.getLogger(__name__)


class UnsafeSelfdestructDetector(Detector):
    _detections: Set[DetectorResult]

    def __init__(self):
        self._detections = set()

    def detect(self) -> List[DetectorResult]:
        return list(self._detections)

    def visit_function_call(self, node: ir.FunctionCall):
        from woke.analysis.ownable import statement_is_publicly_executable

        if node.function_called not in {
            ir.enums.GlobalSymbolsEnum.SELFDESTRUCT,
            ir.enums.GlobalSymbolsEnum.SUICIDE,
        }:
            return

        current_node = node
        while current_node is not None:
            if isinstance(current_node, ir.StatementAbc):
                break
            current_node = current_node.parent
        if current_node is None:
            return
        if not statement_is_publicly_executable(current_node):
            return

        self._detections.add(
            DetectorResult(
                Detection(node, "Selfdestruct call is not protected"),
                impact=DetectionImpact.HIGH,
                confidence=DetectionConfidence.MEDIUM,
            )
        )

    @detector.command("unsafe-selfdestruct")
    def cli(self):
        """
        Selfdestruct call is not protected.
        """
        pass
