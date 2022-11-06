import logging
from typing import List, Set

from woke.analysis.detectors import DetectorAbc, DetectorResult, detector
from woke.analysis.detectors.ownable import statement_is_publicly_executable
from woke.ast.enums import GlobalSymbolsEnum
from woke.ast.ir.expression.function_call import FunctionCall
from woke.ast.ir.statement.abc import StatementAbc

logger = logging.getLogger(__name__)


@detector(-100, "unsafe-selfdestruct")
class UnsafeSelfdestructDetector(DetectorAbc):
    """
    Selfdestruct call is not protected.
    """

    _detections: Set[DetectorResult]

    def __init__(self):
        self._detections = set()

    def report(self) -> List[DetectorResult]:
        return list(self._detections)

    def visit_function_call(self, node: FunctionCall):
        if node.function_called not in {
            GlobalSymbolsEnum.SELFDESTRUCT,
            GlobalSymbolsEnum.SUICIDE,
        }:
            return

        current_node = node
        while current_node is not None:
            if isinstance(current_node, StatementAbc):
                break
            current_node = current_node.parent
        if current_node is None:
            return
        if not statement_is_publicly_executable(current_node):
            return

        self._detections.add(DetectorResult(node, "Selfdestruct call is not protected"))
