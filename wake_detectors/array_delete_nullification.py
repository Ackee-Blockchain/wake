from __future__ import annotations

from typing import List

import wake.ir as ir
import wake.ir.types as types
from wake.detectors import (
    Detection,
    DetectorConfidence,
    DetectorImpact,
    Detector,
    DetectorResult,
    detector,
)


class ArrayDeleteNullificationDetector(Detector):
    _detections: List[DetectorResult]

    def __init__(self) -> None:
        self._detections = []

    def detect(self) -> List[DetectorResult]:
        return self._detections

    def visit_unary_operation(self, node: ir.UnaryOperation):
        if node.operator == ir.enums.UnaryOpOperator.DELETE:
            # Check if we're deleting from an array: delete arr[index]
            if isinstance(node.sub_expression, ir.IndexAccess):
                if isinstance(node.sub_expression.base_expression.type, types.Array):
                    self._detections.append(
                        DetectorResult(
                            Detection(
                                node,
                                "Delete on array element only nullifies it, does not remove from array",
                            ),
                            impact=DetectorImpact.INFO,
                            confidence=DetectorConfidence.LOW,
                        )
                    )

    @detector.command(name="array-delete-nullification")
    def cli(self) -> None:
        pass
