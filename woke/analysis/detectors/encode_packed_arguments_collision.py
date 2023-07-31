from typing import List, Set

from woke.analysis.detectors import DetectorAbc, DetectorResult, detector
from woke.ast.enums import GlobalSymbolsEnum
from woke.ast.ir.expression.function_call import FunctionCall
from woke.ast.ir.expression.member_access import MemberAccess
from woke.ast.types import Array, Bytes, String

BLACKLISTED_TYPES = {Array: lambda x: x.length is None, String: None, Bytes: None}


@detector(-1035, "encode-packed-arguments-collision")
class EncodePackedArgumentsCollisionDetector(DetectorAbc):
    """
    Detects when abi.encodePacked uses two or more dynamically sized types.
    """

    _detections: Set[DetectorResult]

    def __init__(self):
        self._detections = set()

    def report(self) -> List[DetectorResult]:
        return list(self._detections)

    def visit_member_access(self, node: MemberAccess):
        if node.referenced_declaration != GlobalSymbolsEnum.ABI_ENCODE_PACKED:
            return
        if not isinstance(node.parent, FunctionCall):
            return

        var_types_cnt = 0
        for arg in node.parent.arguments:
            for t in BLACKLISTED_TYPES:
                if isinstance(arg.type, t) and (
                    BLACKLISTED_TYPES[t] is None or BLACKLISTED_TYPES[t](arg.type)
                ):
                    var_types_cnt += 1
                    continue

        if var_types_cnt < 2:
            return

        self._detections.add(
            DetectorResult(
                node, "`abi.encodePacked` call with at least two dynamic types detected"
            )
        )
