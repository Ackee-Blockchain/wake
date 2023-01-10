from collections import deque
from itertools import chain
from typing import Deque, List, Set

from woke.analysis.detectors import DetectorAbc, DetectorResult, detector
from woke.ast.enums import GlobalSymbolsEnum, StateMutability
from woke.ast.ir.declaration.function_definition import FunctionDefinition
from woke.ast.ir.expression.function_call import FunctionCall
from woke.ast.ir.expression.member_access import MemberAccess
from woke.ast.ir.meta.identifier_path import IdentifierPathPart
from woke.ast.ir.statement.inline_assembly import ExternalReference


@detector(-1031, "msg-value-nonpayable-function")
class MsgValueNonpayableFunctionDetector(DetectorAbc):
    _detections: List[DetectorResult]

    def __init__(self):
        self._detections = []

    def report(self) -> List[DetectorResult]:
        return self._detections

    def visit_member_access(self, node: MemberAccess):
        if node.referenced_declaration != GlobalSymbolsEnum.MSG_VALUE:
            return

        func = node
        while func is not None:
            if isinstance(func, FunctionDefinition):
                break
            func = func.parent

        if func is None:
            return

        if func.state_mutability == StateMutability.PAYABLE:
            return

        visited: Set[FunctionDefinition] = {func}
        queue: Deque[FunctionDefinition] = deque([func])

        while len(queue) > 0:
            func = queue.pop()
            for f in chain(func.base_functions, func.child_functions):
                if isinstance(f, FunctionDefinition) and f not in visited:
                    visited.add(f)
                    queue.append(f)

            for ref in func.references:
                if isinstance(ref, IdentifierPathPart):
                    func_call = ref.underlying_node
                elif isinstance(ref, ExternalReference):
                    func_call = ref.inline_assembly
                else:
                    func_call = ref
                while func_call is not None:
                    if (
                        isinstance(func_call, FunctionCall)
                        and func_call.function_called == func
                    ):
                        break
                    func_call = func_call.parent

                if func_call is None:
                    continue

                other_func = func_call
                while other_func is not None:
                    if isinstance(other_func, FunctionDefinition):
                        break
                    other_func = other_func.parent

                if other_func is None or other_func in visited:
                    continue

                if other_func.state_mutability == StateMutability.PAYABLE:
                    return

                queue.append(other_func)

        self._detections.append(
            DetectorResult(
                node,
                "`msg.value` used in a function that is never called from a payable function",
            )
        )
