from typing import List

from woke.analysis.detectors import DetectorAbc, DetectorResult, detector
from woke.ast.ir.declaration.function_definition import FunctionDefinition


@detector(-1037, "underscore-function-not-private")
class UnderscoreFunctionNotPrivateDetector(DetectorAbc):
    """
    Detects when a function name starts with an underscore but is not private/internal.
    """

    _detections: List[DetectorResult]

    def __init__(self):
        self._detections = []

    def report(self) -> List[DetectorResult]:
        return self._detections

    def visit_function_definition(self, node: FunctionDefinition):
        if node.name.startswith("_") and node.visibility in {"public", "external"}:
            self._detections.append(
                DetectorResult(
                    node,
                    "Function name starts with underscore but is not private/internal",
                )
            )
