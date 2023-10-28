TEMPLATE = """from __future__ import annotations

from typing import List

import networkx as nx
import rich_click as click
import wake.ir as ir
import wake.ir.types as types
from wake.detectors import (
    Detection,
    DetectionConfidence,
    DetectionImpact,
    Detector,
    DetectorResult,
    detector,
)


class {class_name}(Detector):
    def detect(self) -> List[DetectorResult]:
        return []

    @detector.command(name="{command_name}")
    def cli(self) -> None:
        pass
"""
