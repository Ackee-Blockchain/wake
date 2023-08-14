from typing import List, Optional, Set, Tuple

from woke.analysis.detectors import DetectorAbc, DetectorResult, detector
from woke.ast.ir.expression.abc import ExpressionAbc
from woke.ast.ir.expression.binary_operation import BinaryOperation
from woke.ast.ir.expression.conditional import Conditional
from woke.ast.ir.expression.identifier import Identifier
from woke.ast.ir.expression.index_access import IndexAccess
from woke.ast.ir.expression.index_range_access import IndexRangeAccess
from woke.ast.ir.expression.literal import Literal
from woke.ast.ir.expression.member_access import MemberAccess
from woke.ast.ir.expression.tuple_expression import TupleExpression
from woke.ast.ir.statement.expression_statement import ExpressionStatement

DEAD_CODE_EXPRS = (
    Identifier,
    IndexAccess,
    IndexRangeAccess,
    Literal,
    MemberAccess,
)


def _check_dead_components(components: Tuple[Optional[ExpressionAbc], ...]):
    all_dead = True
    for comp in components:
        if any(isinstance(comp, dc) for dc in DEAD_CODE_EXPRS):
            continue
        elif isinstance(comp, TupleExpression):
            all_dead = _check_dead_components(comp.components)
            continue
        elif isinstance(comp, Conditional):
            all_dead = _check_dead_components(
                (comp.condition, comp.true_expression, comp.false_expression)
            )
            continue
        elif isinstance(comp, BinaryOperation):
            all_dead = _check_dead_components(
                (comp.left_expression, comp.right_expression)
            )
            continue
        all_dead = False
    if all_dead:
        return True
    return False


@detector(-1038, "dead-code")
class DeadCodeDetector(DetectorAbc):
    """
    Detects code that does nothing (dead code).
    """

    _detections: Set[DetectorResult]

    def __init__(self):
        self._detections = set()

    def report(self) -> List[DetectorResult]:
        return list(self._detections)

    def visit_expression_statement(self, node: ExpressionStatement):
        if _check_dead_components((node.expression,)):
            self._detections.add(
                DetectorResult(node, f"Expression does nothing (dead code)")
            )
