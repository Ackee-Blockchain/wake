from typing import List, Set

from woke.analysis.detectors import DetectorAbc, DetectorResult, detector
from woke.ast.enums import GlobalSymbolsEnum, StateMutability
from woke.ast.ir.declaration.function_definition import FunctionDefinition
from woke.ast.ir.expression.member_access import MemberAccess


@detector(-1033, "msg-sender-view-function")
class MsgSenderViewFunctionDetector(DetectorAbc):
    """
    Detects when `msg.sender` is used in a view function
    """

    _detections: Set[DetectorResult]

    def __init__(self):
        self._detections = set()

    def report(self) -> List[DetectorResult]:
        return list(self._detections)

    def visit_member_access(self, node: MemberAccess):
        if node.referenced_declaration != GlobalSymbolsEnum.MSG_SENDER:
            return

        func = node
        while func is not None:
            if isinstance(func, FunctionDefinition):
                break
            func = func.parent

        if func is None:
            return

        if func.state_mutability != StateMutability.VIEW:
            return

        self._detections.add(
            DetectorResult(node, "`msg.sender` used in a view function")
        )
