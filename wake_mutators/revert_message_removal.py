from wake.mutators.api import Mutator
from wake.ir.expressions.function_call import FunctionCall
from wake.ir.enums import GlobalSymbol


class RevertMessageRemoval(Mutator):
    """Replace revert("...") with revert()."""

    name = "revert_message_removal"
    description = "Replace revert(message) with revert()"

    def visit_function_call(self, node: FunctionCall):
        if node.function_called == GlobalSymbol.REVERT and len(node.arguments) != 0:
            self._add(
                node=node,
                original=node.source,
                replacement="revert()",
                description="Remove revert message",
            )
