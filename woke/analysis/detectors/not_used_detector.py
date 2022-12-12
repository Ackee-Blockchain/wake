from typing import List, Set

from woke.analysis.detectors import DetectorAbc, DetectorResult, detector
from woke.ast.enums import ContractKind
from woke.ast.ir.declaration.contract_definition import ContractDefinition


@detector(-1040, "not-used")
class NotUsedDetector(DetectorAbc):
    """
    Detects abstract contracts, interfaces and libraries that are not used.
    """

    _detections: Set[DetectorResult]

    def __init__(self):
        self._detections = set()

    def report(self) -> List[DetectorResult]:
        return list(self._detections)

    def visit_contract_definition(self, node: ContractDefinition):
        if (node.abstract or node.kind in ContractKind.INTERFACE) and len(
            node.child_contracts
        ) == 0:
            self._detections.add(DetectorResult(node, "Contract not used"))
        elif node.kind == ContractKind.LIBRARY:
            used = False
            for fn in node.functions:
                if len(list(fn.get_all_references(include_declarations=False))) > 0:
                    used = True
            if not used:
                self._detections.add(DetectorResult(node, "Library not used"))
