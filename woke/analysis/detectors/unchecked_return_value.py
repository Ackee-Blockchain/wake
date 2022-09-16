from typing import Optional

import woke.ast.types as types
from woke.analysis.detectors import DetectorResult, detector
from woke.ast.enums import UnaryOpOperator
from woke.ast.ir.expression.assignment import Assignment
from woke.ast.ir.expression.conditional import Conditional
from woke.ast.ir.expression.function_call import FunctionCall
from woke.ast.ir.expression.function_call_options import FunctionCallOptions
from woke.ast.ir.expression.index_access import IndexAccess
from woke.ast.ir.expression.index_range_access import IndexRangeAccess
from woke.ast.ir.expression.unary_operation import UnaryOperation
from woke.ast.ir.statement.expression_statement import ExpressionStatement


@detector(FunctionCall, -1000, "unchecked-function-return-value")
def detect_unchecked_return_value(ir_node: FunctionCall) -> Optional[DetectorResult]:
    """
    Return value of a function call is ignored.
    """
    t = ir_node.type
    has_return_value = not (isinstance(t, types.Tuple) and len(t.components) == 0)
    if not has_return_value:
        return None

    # TODO external call in try statement

    node = ir_node
    nodes = []
    is_expression_statement = False
    while node is not None:
        if isinstance(node, ExpressionStatement):
            is_expression_statement = True
            break
        nodes.append(node)
        node = node.parent

        if isinstance(node, (Assignment, FunctionCall, FunctionCallOptions)):
            return None
        elif isinstance(node, Conditional):
            if node.condition == nodes[-1]:
                return None
        elif isinstance(node, IndexAccess):
            if node.index_expression == nodes[-1]:
                return None
        elif isinstance(node, IndexRangeAccess):
            if node.start_expression == nodes[-1] or node.end_expression == nodes[-1]:
                return None
        elif isinstance(node, UnaryOperation):
            if node.operator in {
                UnaryOpOperator.PLUS_PLUS,
                UnaryOpOperator.MINUS_MINUS,
                UnaryOpOperator.DELETE,
            }:
                return None

    if not is_expression_statement:
        return None

    return DetectorResult(ir_node, "Unchecked return value")
