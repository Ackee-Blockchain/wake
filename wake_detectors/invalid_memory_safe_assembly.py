from __future__ import annotations

import re
from typing import List

import rich_click as click

import wake.ir as ir
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


class InvalidMemorySafeAssemblyDetector(Detector):
    _detections: List[DetectorResult]

    def __init__(self) -> None:
        self._detections = []

    def detect(self) -> List[DetectorResult]:
        return self._detections

    def visit_inline_assembly(self, node: ir.InlineAssembly):
        """
        Visit inline assembly blocks and check for invalid memory-safe assembly comments.
        """
        source_code = node.source_unit.file_source
        assembly_start = node.byte_location[0]
        code_before_assembly = source_code[:assembly_start].decode("utf-8", errors="ignore")
        lines = code_before_assembly.splitlines()
        # Scan up to 10 lines above the assembly block
        i = 1
        max_scan = min(10, len(lines))
        while i <= max_scan:
            line = lines[-i].rstrip()
            # Block comment end
            if line.endswith("*/"):
                block = [line]
                for j in range(i + 1, min(i + 20, len(lines) + 1)):
                    block_line = lines[-j].rstrip()
                    block.append(block_line)
                    if block_line.lstrip().startswith("/*"):
                        break
                block_comment = "\n".join(reversed(block))
                if "@solidity memory-safe-assembly" in block_comment:
                    if not block_comment.lstrip().startswith("/**"):
                        self._detections.append(
                            DetectorResult(
                                Detection(
                                    node,
                                    "Invalid memory-safe assembly comment. Use `/// @solidity memory-safe-assembly` or `/** @solidity memory-safe-assembly */` instead of `/* @solidity memory-safe-assembly */`.",
                                ),
                                impact=DetectorImpact.INFO,
                                confidence=DetectorConfidence.HIGH,
                                uri=generate_detector_uri(
                                    name="invalid-memory-safe-assembly",
                                    version=self.extra["package_versions"]["eth-wake"],
                                ),
                            )
                        )
                    return
                i += len(block)
                continue
            # Single-line or multi-line // comments
            if line.lstrip().startswith("//"):
                comment_block = []
                for j in range(i, max_scan + 1):
                    l = lines[-j].lstrip()
                    if l.startswith("//"):
                        comment_block.append(l)
                    else:
                        break
                comment_block = list(reversed(comment_block))
                for comment_line in comment_block:
                    if "@solidity memory-safe-assembly" in comment_line:
                        if not comment_line.startswith("///"):
                            self._detections.append(
                                DetectorResult(
                                    Detection(
                                        node,
                                        "Invalid memory-safe assembly comment. Use `/// @solidity memory-safe-assembly` or `/** @solidity memory-safe-assembly */` instead of `// @solidity memory-safe-assembly`.",
                                    ),
                                    impact=DetectorImpact.INFO,
                                    confidence=DetectorConfidence.HIGH,
                                    uri=generate_detector_uri(
                                        name="invalid-memory-safe-assembly",
                                        version=self.extra["package_versions"]["eth-wake"],
                                    ),
                                )
                            )
                        return
                i += len(comment_block)
                continue
            # Otherwise, continue
            i += 1

    @detector.command(name="invalid-memory-safe-assembly")
    def cli(self) -> None:
        """
        Invalid memory-safe assembly tag
        """ 