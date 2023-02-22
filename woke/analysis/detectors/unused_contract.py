from typing import List, Set

from woke.analysis.detectors import DetectorAbc, DetectorResult, detector
from woke.ast.enums import ContractKind
from woke.ast.ir.declaration.contract_definition import ContractDefinition


@detector(-1040, "unused-contract")
class UnusedContractDetector(DetectorAbc):
    """
    Detects abstract contracts, interfaces and libraries that are not used.
    """

    _detections: Set[DetectorResult]

    def __init__(self):
        self._detections = set()

    def report(self) -> List[DetectorResult]:
        return list(self._detections)

    def visit_contract_definition(self, node: ContractDefinition):
        if len(node.references) == 0:
            if node.abstract:
                self._detections.add(
                    DetectorResult(
                        node, "Contract not used", lsp_range=node.name_location
                    )
                )
            elif node.kind == ContractKind.INTERFACE:
                self._detections.add(
                    DetectorResult(
                        node, "Interface not used", lsp_range=node.name_location
                    )
                )
            elif node.kind == ContractKind.LIBRARY:
                self._detections.add(
                    DetectorResult(
                        node, "Library not used", lsp_range=node.name_location
                    )
                )
