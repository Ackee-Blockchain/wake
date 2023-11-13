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


class CallOptionsNotCalledDetector(Detector):
    _detections: List[DetectorResult]

    def __init__(self) -> None:
        self._detections = []

    def detect(self) -> List[DetectorResult]:
        return self._detections

    def visit_function_call_options(self, node: ir.FunctionCallOptions):
        expr = node
        while True:
            if (
                isinstance(expr, ir.MemberAccess)
                and isinstance(expr.parent, ir.FunctionCall)
                and expr.referenced_declaration
                in {
                    ir.enums.GlobalSymbol.FUNCTION_GAS,
                    ir.enums.GlobalSymbol.FUNCTION_VALUE,
                }
            ):
                expr = expr.parent.parent
            elif isinstance(expr, ir.FunctionCallOptions):
                expr = expr.parent
            else:
                break

        if not isinstance(expr, ir.FunctionCall):
            self._detections.append(
                DetectorResult(
                    Detection(node, "Function call options not called"),
                    DetectionImpact.HIGH,
                    DetectionConfidence.HIGH,
                )
            )

    def visit_member_access(self, node: ir.MemberAccess):
        if node.referenced_declaration not in {
            ir.enums.GlobalSymbol.FUNCTION_GAS,
            ir.enums.GlobalSymbol.FUNCTION_VALUE,
        }:
            return

        expr = node
        while True:
            if (
                isinstance(expr, ir.MemberAccess)
                and isinstance(expr.parent, ir.FunctionCall)
                and expr.referenced_declaration
                in {
                    ir.enums.GlobalSymbol.FUNCTION_GAS,
                    ir.enums.GlobalSymbol.FUNCTION_VALUE,
                }
            ):
                expr = expr.parent.parent
            elif isinstance(expr, ir.FunctionCallOptions):
                expr = expr.parent
            else:
                break

        if not isinstance(expr, ir.FunctionCall):
            self._detections.append(
                DetectorResult(
                    Detection(node, "Function call options not called"),
                    DetectionImpact.HIGH,
                    DetectionConfidence.HIGH,
                )
            )

    @detector.command(name="call-options-not-called")
    def cli(self) -> None:
        """
        Detect when call options (`gas`, `value` or `salt`) are not called.
        """
