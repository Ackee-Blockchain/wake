TEMPLATE = """from __future__ import annotations

from typing import List

import networkx as nx
import rich_click as click
import wake.ir as ir
import wake.ir.types as types
from wake.cli import SolidityName
from wake.detectors import (
    Detection,
    DetectorConfidence,
    DetectorImpact,
    Detector,
    DetectorResult,
    detector,
)


class {class_name}(Detector):
    _detections: List[DetectorResult]

    def __init__(self) -> None:
        self._detections = []

    def detect(self) -> List[DetectorResult]:
        return self._detections

    @detector.command(name="{command_name}")
    def cli(self) -> None:
        pass
"""
