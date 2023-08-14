TEMPLATE = """from __future__ import annotations

from typing import List

import rich_click as click
import woke.ir as ir
import woke.ir.types as types
from woke.detectors import (
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
