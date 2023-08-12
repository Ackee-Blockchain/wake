from typing import List, Set

import woke.ir.types as types
from woke.analysis.detectors import DetectorAbc, DetectorResult, detector
from woke.ir import (
    Assignment,
    Conditional,
    ExpressionStatement,
    FunctionCall,
    FunctionCallOptions,
    IndexAccess,
    IndexRangeAccess,
    UnaryOperation,
)
from woke.ir.enums import UnaryOpOperator


@detector(-1000, "unchecked-return-value")
class UncheckedReturnValueDetector(DetectorAbc):
    """
    Return value of a function call is ignored.
    """

    _detections: Set[DetectorResult]

    def __init__(self):
        self._detections = set()

    def report(self) -> List[DetectorResult]:
        return list(self._detections)

    def visit_function_call(self, node: FunctionCall):
        t = node.type
        has_return_value = not (isinstance(t, types.Tuple) and len(t.components) == 0)
        if not has_return_value:
            return

        # TODO external call in try statement

        current_node = node
        nodes = []
        is_expression_statement = False
        while current_node is not None:
            if isinstance(current_node, ExpressionStatement):
                is_expression_statement = True
                break
            nodes.append(current_node)
            current_node = current_node.parent

            if isinstance(
                current_node, (Assignment, FunctionCall, FunctionCallOptions)
            ):
                return
            elif isinstance(current_node, Conditional):
                if current_node.condition == nodes[-1]:
                    return
            elif isinstance(current_node, IndexAccess):
                if current_node.index_expression == nodes[-1]:
                    return
            elif isinstance(current_node, IndexRangeAccess):
                if (
                    current_node.start_expression == nodes[-1]
                    or current_node.end_expression == nodes[-1]
                ):
                    return
            elif isinstance(current_node, UnaryOperation):
                if current_node.operator in {
                    UnaryOpOperator.PLUS_PLUS,
                    UnaryOpOperator.MINUS_MINUS,
                    UnaryOpOperator.DELETE,
                }:
                    return

        if not is_expression_statement:
            return

        self._detections.add(DetectorResult(node, "Unchecked return value"))
