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


class EmptyByteArrayCopyBugDetector(Detector):
    _detections: List[DetectorResult]

    def __init__(self) -> None:
        self._detections = []

    def detect(self) -> List[DetectorResult]:
        return self._detections

    def visit_member_access(self, node: ir.MemberAccess):
        # no need to check for .length assignment since it's not possible to assign length in the minimal version
        # supported by Wake
        if node.referenced_declaration != ir.enums.GlobalSymbol.BYTES_PUSH:
            return

        # just a sanity check
        if node.statement is None:
            return

        # only .push to storage bytes is affected
        t = node.expression.type
        if (
            not isinstance(t, types.Bytes)
            or t.data_location != ir.enums.DataLocation.STORAGE
        ):
            return

        # .push(c) is not affected
        parent = node.parent
        if not isinstance(parent, ir.FunctionCall) or len(parent.arguments) != 0:
            return

        # find an assignment to the variable
        expr = node.expression
        if not isinstance(expr, ir.Identifier) or not isinstance(
            expr.referenced_declaration, ir.VariableDeclaration
        ):
            return

        cfg = node.statement.declaration.cfg

        for ref in expr.referenced_declaration.references:
            if not isinstance(ref, (ir.Identifier, ir.MemberAccess)):
                continue

            # ref not in the same function/modifier
            if (
                ref.statement is None
                or ref.statement.declaration != node.statement.declaration
            ):
                continue

            # storage bytes var not assigned to
            parent = ref.parent
            if not isinstance(parent, ir.Assignment) or parent.left_expression != ref:
                continue

            # only copy from calldata/memory is affected
            t = parent.right_expression.type
            if (
                not isinstance(t, types.Bytes)
                or t.data_location == ir.enums.DataLocation.STORAGE
            ):
                continue

            # .push() may happen after the assignment
            if (
                cfg.is_reachable(ref.statement, node.statement)
                or ref.statement == node.statement
            ):
                self._detections.append(
                    DetectorResult(
                        Detection(
                            node.parent,
                            ".push() may append non-zero byte because of compiler bug",
                        ),
                        DetectorImpact.MEDIUM,
                        DetectorConfidence.MEDIUM,
                        uri=generate_detector_uri(
                            name="empty-byte-array-copy-bug",
                            version=self.extra["package_versions"]["eth-wake"],
                        ),
                    )
                )
                return

    @detector.command(name="empty-byte-array-copy-bug")
    def cli(self) -> None:
        """
        Empty byte array copy compiler bug in Solidity < 0.7.14
        """
