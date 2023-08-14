from __future__ import annotations

from typing import List, Set

import woke.ir as ir
from woke.detectors import (
    Detection,
    DetectionConfidence,
    DetectionImpact,
    Detector,
    DetectorResult,
    detector,
)


class UnusedContractDetector(Detector):
    _detections: Set[Detection]

    def __init__(self):
        self._detections = set()

    def detect(self) -> List[DetectorResult]:
        return [
            DetectorResult(
                d, impact=DetectionImpact.WARNING, confidence=DetectionConfidence.HIGH
            )
            for d in self._detections
        ]

    def visit_contract_definition(self, node: ir.ContractDefinition):
        if len(node.references) == 0:
            if node.abstract:
                self._detections.add(
                    Detection(node, "Contract not used", lsp_range=node.name_location)
                )
            elif node.kind == ir.enums.ContractKind.INTERFACE:
                self._detections.add(
                    Detection(node, "Interface not used", lsp_range=node.name_location)
                )
            elif node.kind == ir.enums.ContractKind.LIBRARY:
                self._detections.add(
                    Detection(node, "Library not used", lsp_range=node.name_location)
                )

    @detector.command("unused-contract")
    def cli(self):
        """
        Detects abstract contracts, interfaces and libraries that are not used.
        """
        pass
