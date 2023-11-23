from __future__ import annotations

from collections import deque
from typing import Deque, List, Set

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


class MsgValueNonpayableFunctionDetector(Detector):
    _detections: List[DetectorResult]

    def __init__(self) -> None:
        self._detections = []

    def detect(self) -> List[DetectorResult]:
        return self._detections

    def visit_member_access(self, node: ir.MemberAccess):
        from itertools import chain

        if node.referenced_declaration != ir.enums.GlobalSymbol.MSG_VALUE:
            return

        # safety check
        if node.statement is None:
            return

        visited: Set[ir.FunctionDefinition] = set()
        queue: Deque[ir.FunctionDefinition] = deque()

        decl = node.statement.declaration
        if isinstance(decl, ir.ModifierDefinition):
            for ref in decl.references:
                if isinstance(ref, ir.ExternalReference):
                    continue
                elif isinstance(ref, ir.IdentifierPathPart):
                    ref = ref.underlying_node

                if (
                    isinstance(ref.parent, ir.ModifierInvocation)
                    and ref.parent.parent not in visited
                ):
                    func = ref.parent.parent
                    assert isinstance(func, ir.FunctionDefinition)
                    if func.state_mutability == ir.enums.StateMutability.PAYABLE:
                        return
                    visited.add(func)
                    queue.append(func)
        else:
            if decl.state_mutability == ir.enums.StateMutability.PAYABLE:
                return
            visited.add(decl)
            queue.append(decl)

        while len(queue) > 0:
            func = queue.pop()
            for f in chain(func.base_functions, func.child_functions):
                if isinstance(f, ir.FunctionDefinition) and f not in visited:
                    visited.add(f)
                    queue.append(f)

            for ref in func.references:
                if isinstance(ref, ir.IdentifierPathPart):
                    func_call = ref.underlying_node
                elif isinstance(ref, ir.ExternalReference):
                    func_call = ref.inline_assembly
                else:
                    func_call = ref
                while func_call is not None:
                    if (
                        isinstance(func_call, ir.FunctionCall)
                        and func_call.function_called == func
                    ):
                        break
                    func_call = func_call.parent

                if func_call is None or func_call.statement is None:
                    continue

                other_func = func_call.statement.declaration
                # TODO: modifiers
                if other_func in visited or isinstance(
                    other_func, ir.ModifierDefinition
                ):
                    continue

                if other_func.state_mutability == ir.enums.StateMutability.PAYABLE:
                    return

                queue.append(other_func)

        self._detections.append(
            DetectorResult(
                Detection(
                    node,
                    "msg.value used in function that is never called from payable function",
                ),
                impact=DetectorImpact.WARNING,
                confidence=DetectorConfidence.HIGH,
                uri=generate_detector_uri(
                    name="msg-value-nonpayable-function",
                    version=self.extra["package_versions"]["eth-wake"],
                ),
            )
        )

    @detector.command(name="msg-value-nonpayable-function")
    def cli(self) -> None:
        """
        msg.value used in non-payable function
        """
