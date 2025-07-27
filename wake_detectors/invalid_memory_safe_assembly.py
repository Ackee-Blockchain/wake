from __future__ import annotations

from typing import List

import wake.ir as ir
from wake.detectors import (
    Detection,
    Detector,
    DetectorConfidence,
    DetectorImpact,
    DetectorResult,
    detector,
)
from wake_detectors.utils import generate_detector_uri


def _find_nearest_comment_blocks(node: ir.InlineAssembly) -> List[str]:
    """
    Find the nearest non-NatSpec comment blocks immediately preceding the inline assembly block.
    Non-NatSpec comments are // and /* */ style comments (not /// or /** */).

    Returns:
        List of comment content strings.
    """
    import re

    source_code = node.source_unit.file_source
    declaration_start = node.byte_location[0]
    code_before_declaration = source_code[:declaration_start]
    code_str = code_before_declaration.decode("utf-8", errors="ignore")

    comment_blocks = []

    # Match // comments (but not /// comments) - must start with exactly //
    single_line_pattern = r"^[ \t]*//(?!/)[^\n]*$"
    lines = code_str.splitlines()

    # Find the last set of consecutive // comments before the assembly
    consecutive_comments = []
    for i in reversed(range(len(lines))):
        line = lines[i]
        if re.match(single_line_pattern, line):
            consecutive_comments.insert(0, line)
        elif line.strip() == "":
            # Empty line, continue
            continue
        else:
            # Non-comment line, stop searching
            break

    if consecutive_comments:
        comment_content = "\n".join(consecutive_comments)
        comment_blocks.append(comment_content)

    # Match /* */ style comments (but not /** */ comments)
    multi_line_pattern = r"/\*(?!\*).*?\*/"
    multi_line_matches = list(re.finditer(multi_line_pattern, code_str, re.DOTALL))
    if multi_line_matches:
        last = multi_line_matches[-1]
        # Check if followed only by whitespace
        if code_str[last.end() :].strip() == "":
            comment_content = code_str[last.start() : last.end()]
            comment_blocks.append(comment_content)

    return comment_blocks


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
        import re

        comment_blocks = _find_nearest_comment_blocks(node)

        for comment_content in comment_blocks:
            if re.search(r"@solidity\s+memory-safe-assembly", comment_content):
                self._detections.append(
                    DetectorResult(
                        Detection(
                            node,
                            "Non-NatSpec comments are ignored for @solidity memory-safe-assembly",
                        ),
                        impact=DetectorImpact.INFO,
                        confidence=DetectorConfidence.HIGH,
                        uri=generate_detector_uri(
                            name="invalid-memory-safe-assembly",
                            version=self.extra["package_versions"]["eth-wake"],
                        ),
                    )
                )

    @detector.command(name="invalid-memory-safe-assembly")
    def cli(self) -> None:
        """
        Invalid memory-safe assembly tag
        """
