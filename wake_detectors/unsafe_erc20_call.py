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


class UnsafeErc20CallDetector(Detector):
    _detections: List[DetectorResult]

    def __init__(self) -> None:
        self._detections = []

    def detect(self) -> List[DetectorResult]:
        return self._detections

    def visit_member_access(self, node: ir.MemberAccess):
        t = node.type
        if (
            not isinstance(t, types.Function)
            or t.kind != ir.enums.FunctionTypeKind.EXTERNAL
        ):
            return

        func_call = node.parent
        while func_call is not None and not isinstance(
            func_call, (ir.FunctionCall, ir.StatementAbc)
        ):
            func_call = func_call.parent

        if not isinstance(func_call, ir.FunctionCall):
            return

        ref_decl = func_call.function_called
        if not isinstance(ref_decl, ir.FunctionDefinition):
            return

        if ref_decl.function_selector in {
            bytes.fromhex("a9059cbb"),  # transfer(address,uint256)
            bytes.fromhex("095ea7b3"),  # approve(address,uint256)
            bytes.fromhex("23b872dd"),  # transferFrom(address,address,uint256)
        }:
            self._detections.append(
                DetectorResult(
                    Detection(
                        func_call,
                        "Unsafe variant of ERC-20 call",
                    ),
                    impact=DetectorImpact.MEDIUM,
                    confidence=DetectorConfidence.HIGH,
                    uri=generate_detector_uri(
                        name="unsafe-erc20-call",
                        version=self.extra["package_versions"]["eth-wake"],
                    ),
                )
            )

    @detector.command(name="unsafe-erc20-call")
    def cli(self) -> None:
        """
        Unsafe variant of ERC-20 call
        """
