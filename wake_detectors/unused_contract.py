from __future__ import annotations

from typing import List, Set

import click

import wake.ir as ir
from wake.detectors import (
    Detection,
    DetectionConfidence,
    DetectionImpact,
    Detector,
    DetectorResult,
    detector,
)


class UnusedContractDetector(Detector):
    _detections: Set[Detection]
    _abstract: bool
    _interface: bool
    _library: bool

    def __init__(self):
        self._detections = set()

    def detect(self) -> List[DetectorResult]:
        return [
            DetectorResult(
                d,
                impact=DetectionImpact.INFO,
                confidence=DetectionConfidence.HIGH,
                url="https://ackeeblockchain.com/wake/docs/latest/static-analysis/detectors/unused-contract",
            )
            for d in self._detections
        ]

    def visit_contract_definition(self, node: ir.ContractDefinition):
        if len(node.references) == 0:
            if node.abstract and self._abstract:
                self._detections.add(Detection(node, "Abstract contract not used"))
            elif node.kind == ir.enums.ContractKind.INTERFACE and self._interface:
                self._detections.add(Detection(node, "Interface not used"))
            elif node.kind == ir.enums.ContractKind.LIBRARY and self._library:
                self._detections.add(Detection(node, "Library not used"))

    @detector.command("unused-contract")
    @click.option(
        "--abstract/--no-abstract",
        is_flag=True,
        default=True,
        help="Detect unused abstract contracts.",
    )
    @click.option(
        "--interface/--no-interface",
        is_flag=True,
        default=True,
        help="Detect unused interfaces.",
    )
    @click.option(
        "--library/--no-library",
        is_flag=True,
        default=True,
        help="Detect unused libraries.",
    )
    def cli(self, abstract: bool, interface: bool, library: bool):
        """
        Detect unused abstract contracts, interfaces and libraries.
        """
        self._abstract = abstract
        self._interface = interface
        self._library = library
