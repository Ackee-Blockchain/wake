from __future__ import annotations

from typing import List, Set

import wake.ir as ir
import wake.ir.types as types
from wake.detectors import (
    Detection,
    Detector,
    DetectorConfidence,
    DetectorImpact,
    DetectorResult,
    detector,
)
from wake_detectors.utils import generate_detector_uri


class UncheckedReturnValueDetector(Detector):
    _detections: Set[DetectorResult]

    def __init__(self):
        self._detections = set()

    def detect(self) -> List[DetectorResult]:
        return list(self._detections)

    def visit_function_call(self, node: ir.FunctionCall):
        t = node.type
        has_return_value = not (isinstance(t, types.Tuple) and len(t.components) == 0)
        if not has_return_value:
            return

        current_node = node
        nodes = []
        return_value_unused = False
        while current_node is not None:
            if isinstance(current_node, ir.ExpressionStatement):
                return_value_unused = True
                break
            elif isinstance(current_node, ir.TryStatement):
                success_clause = next(
                    c for c in current_node.clauses if c.error_name == ""
                )
                if success_clause.parameters is None:
                    return_value_unused = True
                break
            elif isinstance(current_node, ir.StatementAbc):
                break
            nodes.append(current_node)
            current_node = current_node.parent

            if isinstance(
                current_node, (ir.Assignment, ir.FunctionCall, ir.FunctionCallOptions)
            ):
                return
            elif isinstance(current_node, ir.Conditional):
                if current_node.condition == nodes[-1]:
                    return
            elif isinstance(current_node, ir.IndexAccess):
                if current_node.index_expression == nodes[-1]:
                    return
            elif isinstance(current_node, ir.IndexRangeAccess):
                if (
                    current_node.start_expression == nodes[-1]
                    or current_node.end_expression == nodes[-1]
                ):
                    return
            elif isinstance(current_node, ir.UnaryOperation):
                if current_node.operator in {
                    ir.enums.UnaryOpOperator.PLUS_PLUS,
                    ir.enums.UnaryOpOperator.MINUS_MINUS,
                    ir.enums.UnaryOpOperator.DELETE,
                }:
                    return

        func_called = node.function_called
        impact = DetectorImpact.WARNING
        confidence = DetectorConfidence.HIGH
        if isinstance(
            func_called, ir.FunctionDefinition
        ) and func_called.function_selector in {
            bytes.fromhex("a9059cbb"),  # transfer(address,uint256)
            bytes.fromhex("23b872dd"),  # transferFrom(address,address,uint256)
        }:
            impact = DetectorImpact.HIGH
            confidence = DetectorConfidence.MEDIUM
        elif func_called in {
            ir.enums.GlobalSymbol.ADDRESS_CALL,
            ir.enums.GlobalSymbol.ADDRESS_SEND,
            ir.enums.GlobalSymbol.ADDRESS_TRANSFER,
            ir.enums.GlobalSymbol.ADDRESS_DELEGATECALL,
            ir.enums.GlobalSymbol.ADDRESS_STATICCALL,
        }:
            impact = DetectorImpact.MEDIUM
            confidence = DetectorConfidence.MEDIUM

        if return_value_unused:
            self._detections.add(
                DetectorResult(
                    Detection(node, "Unchecked return value"),
                    impact=impact,
                    confidence=confidence,
                    uri=generate_detector_uri(
                        name="unchecked-return-value",
                        version=self.extra["package_versions"]["eth-wake"],
                    ),
                )
            )

    @detector.command("unchecked-return-value")
    def cli(self):
        """
        Unchecked function call return value
        """
