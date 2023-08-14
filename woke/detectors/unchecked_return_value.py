from __future__ import annotations

from typing import List, Set

import woke.ir as ir
import woke.ir.types as types
from woke.detectors import (
    Detection,
    DetectionConfidence,
    DetectionImpact,
    Detector,
    DetectorResult,
    detector,
)


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

        # TODO external call in try statement

        current_node = node
        nodes = []
        is_expression_statement = False
        while current_node is not None:
            if isinstance(current_node, ir.ExpressionStatement):
                is_expression_statement = True
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

        if not is_expression_statement:
            return

        self._detections.add(
            DetectorResult(
                Detection(node, "Unchecked return value"),
                impact=DetectionImpact.MEDIUM,
                confidence=DetectionConfidence.HIGH,
            )
        )

    @detector.command("unchecked-return-value")
    def cli(self):
        """
        Return value of a function call is ignored.
        """
        pass
