from __future__ import annotations

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


class FunctionCallOptionsNotCalledDetector(Detector):
    _detections: Set[DetectorResult]

    def __init__(self):
        self._detections = set()

    def detect(self) -> List[DetectorResult]:
        return list(self._detections)

    def visit_function_call_options(self, node: ir.FunctionCallOptions):
        if not isinstance(node.parent, ir.FunctionCall):
            self._detections.add(
                DetectorResult(
                    Detection(node, "Function call options not called"),
                    DetectionImpact.HIGH,
                    DetectionConfidence.HIGH,
                )
            )

    def visit_member_access(self, node: ir.MemberAccess):
        if node.referenced_declaration in {
            ir.enums.GlobalSymbolsEnum.FUNCTION_GAS,
            ir.enums.GlobalSymbolsEnum.FUNCTION_VALUE,
        }:
            parent = node.parent
            assert isinstance(parent, ir.FunctionCall)

            if not isinstance(parent.parent, ir.FunctionCall):
                if (
                    node.referenced_declaration
                    == ir.enums.GlobalSymbolsEnum.FUNCTION_GAS
                ):
                    self._detections.add(
                        DetectorResult(
                            Detection(node, "Function with gas not called"),
                            DetectionImpact.HIGH,
                            DetectionConfidence.HIGH,
                        )
                    )
                else:
                    self._detections.add(
                        DetectorResult(
                            Detection(node, "Function with value not called"),
                            DetectionImpact.HIGH,
                            DetectionConfidence.HIGH,
                        )
                    )

    @detector.command("function-call-options-not-called")
    def cli(self):
        """
        Function with gas or value set actually is not called, e.g. `this.externalFunction.value(targetValue)` or `this.externalFunction{value: targetValue}`.
        """
        pass
