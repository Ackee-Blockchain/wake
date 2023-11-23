from __future__ import annotations

from typing import List

import networkx as nx
import rich_click as click

import wake.ir as ir
import wake.ir.types as types
from wake.detectors import (
    Detection,
    Detector,
    DetectorConfidence,
    DetectorImpact,
    DetectorResult,
    detector,
)
from wake_detectors.utils import generate_detector_uri


class TxOriginDetector(Detector):
    _account_abstraction: bool
    _detections: List[DetectorResult]

    def __init__(self) -> None:
        self._detections = []

    def detect(self) -> List[DetectorResult]:
        return self._detections

    def visit_member_access(self, node: ir.MemberAccess):
        from wake.analysis.expressions import expression_is_global_symbol

        if node.referenced_declaration != ir.enums.GlobalSymbol.TX_ORIGIN:
            return

        if self._account_abstraction:
            self._detections.append(
                DetectorResult(
                    Detection(
                        node,
                        "Use of tx.origin may interfere with ERC-4337 account abstraction",
                    ),
                    impact=DetectorImpact.WARNING,
                    confidence=DetectorConfidence.LOW,
                    uri=generate_detector_uri(
                        name="tx-origin",
                        version=self.extra["package_versions"]["eth-wake"],
                        anchor="account-abstraction",
                    ),
                )
            )

        np = node.parent
        npp = node.parent.parent
        if np is not None and npp is not None:
            if (
                isinstance(np, ir.BinaryOperation)
                and np.operator == ir.enums.BinaryOpOperator.EQ
            ):
                other_expr = (
                    np.right_expression
                    if np.left_expression == node
                    else np.left_expression
                )
                if expression_is_global_symbol(
                    other_expr, ir.enums.GlobalSymbol.MSG_SENDER
                ):
                    return

            elif isinstance(np, ir.IndexAccess):
                if isinstance(npp, ir.BinaryOperation) and npp.operator in {
                    ir.enums.BinaryOpOperator.LT,
                    ir.enums.BinaryOpOperator.GT,
                }:
                    other_expr = (
                        npp.right_expression
                        if npp.left_expression == np
                        else npp.left_expression
                    )
                    if expression_is_global_symbol(
                        other_expr, ir.enums.GlobalSymbol.BLOCK_TIMESTAMP
                    ):
                        return

        self._detections.append(
            DetectorResult(
                Detection(node, "Unsafe usage of tx.origin"),
                impact=DetectorImpact.MEDIUM,
                confidence=DetectorConfidence.LOW,
                uri=generate_detector_uri(
                    name="tx-origin",
                    version=self.extra["package_versions"]["eth-wake"],
                    anchor="phishing-attacks",
                ),
            )
        )

    @detector.command(name="tx-origin")
    @click.option(
        "--account-abstraction/--no-account-abstraction",
        is_flag=True,
        default=True,
        help="Report account abstraction related issues.",
    )
    def cli(self, account_abstraction: bool) -> None:
        """
        Possibly incorrect usage of tx.origin
        """
        self._account_abstraction = account_abstraction
