from __future__ import annotations

from typing import Deque, List, Set

import woke.ir as ir
from woke.detectors import (
    Detection,
    DetectionConfidence,
    DetectionImpact,
    Detector,
    DetectorResult,
    detector,
)


class MsgValueNonpayableFunctionDetector(Detector):
    _detections: List[DetectorResult]

    def __init__(self):
        self._detections = []

    def detect(self) -> List[DetectorResult]:
        return self._detections

    def visit_member_access(self, node):
        from collections import deque
        from itertools import chain

        if node.referenced_declaration != ir.enums.GlobalSymbolsEnum.MSG_VALUE:
            return

        func = node
        while func is not None:
            if isinstance(func, ir.FunctionDefinition):
                break
            func = func.parent

        if func is None:
            return

        if func.state_mutability == ir.enums.StateMutability.PAYABLE:
            return

        visited: Set[ir.FunctionDefinition] = {func}
        queue: Deque[ir.FunctionDefinition] = deque([func])

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

                if func_call is None:
                    continue

                other_func = func_call
                while other_func is not None:
                    if isinstance(other_func, ir.FunctionDefinition):
                        break
                    other_func = other_func.parent

                if other_func is None or other_func in visited:
                    continue

                if other_func.state_mutability == ir.enums.StateMutability.PAYABLE:
                    return

                queue.append(other_func)

        self._detections.append(
            DetectorResult(
                Detection(
                    node,
                    "`msg.value` used in a function that is never called from a payable function",
                ),
                impact=DetectionImpact.MEDIUM,
                confidence=DetectionConfidence.HIGH,
            )
        )

    @detector.command("msg-value-nonpayable-function")
    def cli(self):
        pass
