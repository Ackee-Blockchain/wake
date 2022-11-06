from typing import List, Set

from woke.ast.enums import GlobalSymbolsEnum
from woke.ast.ir.expression.function_call import FunctionCall
from woke.ast.ir.expression.function_call_options import FunctionCallOptions
from woke.ast.ir.expression.member_access import MemberAccess

from .api import DetectorAbc, DetectorResult, detector


@detector(-1002, "function-call-options-not-called")
class FunctionCallOptionsNotCalledDetector(DetectorAbc):
    """
    Function with gas or value set actually is not called, e.g. `this.externalFunction.value(targetValue)` or `this.externalFunction{value: targetValue}`.
    """

    _detections: Set[DetectorResult]

    def __init__(self):
        self._detections = set()

    def report(self) -> List[DetectorResult]:
        return list(self._detections)

    def visit_function_call_options(self, node: FunctionCallOptions):
        if not isinstance(node.parent, FunctionCall):
            self._detections.add(
                DetectorResult(node, "Function call options not called")
            )

    def visit_member_access(self, node: MemberAccess):
        if node.referenced_declaration in {
            GlobalSymbolsEnum.FUNCTION_GAS,
            GlobalSymbolsEnum.FUNCTION_VALUE,
        }:
            parent = node.parent
            assert isinstance(parent, FunctionCall)

            if not isinstance(parent.parent, FunctionCall):
                if node.referenced_declaration == GlobalSymbolsEnum.FUNCTION_GAS:
                    self._detections.add(
                        DetectorResult(node, "Function with gas not called")
                    )
                else:
                    self._detections.add(
                        DetectorResult(node, "Function with value not called")
                    )
