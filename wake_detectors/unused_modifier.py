from __future__ import annotations

from typing import List

import networkx as nx
import rich_click as click

import wake.ir as ir
import wake.ir.types as types
from wake.cli import SolidityName
from wake.detectors import (
    Detection,
    Detector,
    DetectorConfidence,
    DetectorImpact,
    DetectorResult,
    detector,
)
from wake_detectors.utils import generate_detector_uri


class UnusedModifierDetector(Detector):
    _detections: List[DetectorResult]

    def __init__(self) -> None:
        self._detections = []

    def detect(self) -> List[DetectorResult]:
        return self._detections

    def visit_modifier_definition(self, node: ir.ModifierDefinition):
        from wake.analysis.utils import get_all_base_and_child_declarations

        if all(
            len(d.references) == 0 for d in get_all_base_and_child_declarations(node)
        ):
            self._detections.append(
                DetectorResult(
                    Detection(
                        node,
                        "Unused modifier",
                    ),
                    impact=DetectorImpact.INFO,
                    confidence=DetectorConfidence.HIGH,
                    uri=generate_detector_uri(
                        name="unused-modifier",
                        version=self.extra["package_versions"]["eth-wake"],
                    ),
                )
            )

    @detector.command(name="unused-modifier")
    def cli(self) -> None:
        """
        Unused modifier
        """
