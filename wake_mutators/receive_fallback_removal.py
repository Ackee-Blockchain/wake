from wake.mutators.api import Mutator
from wake.ir.declarations.function_definition import FunctionDefinition
from wake.ir.enums import FunctionKind


class ReceiveFallbackRemoval(Mutator):
    """Remove receive() and fallback() functions."""

    name = "receive_fallback_removal"
    description = "Remove receive() and fallback() functions"

    def visit_function_definition(self, node: FunctionDefinition):
        if node.kind not in (FunctionKind.RECEIVE, FunctionKind.FALLBACK):
            return
        self._add(
            node=node,
            original=node.source,
            replacement="",
            description=f"Remove {node.kind.value} function",
        )
