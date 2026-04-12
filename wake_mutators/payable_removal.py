import re

from wake.mutators.api import Mutator
from wake.ir.declarations.function_definition import FunctionDefinition
from wake.ir.enums import StateMutability
from wake.ir.enums import FunctionKind


class PayableRemoval(Mutator):
    """Remove payable mutability from function definitions."""

    name = "payable_removal"
    description = "Remove payable mutability"

    def visit_function_definition(self, node: FunctionDefinition):
        if node.state_mutability != StateMutability.PAYABLE:
            return
        
        if node.kind == FunctionKind.RECEIVE:
            # Receive function must be payable for compilation
            return

        source = node.source
        header_end = source.find("{")
        if header_end == -1:
            header_end = source.find(";")
        if header_end == -1:
            header_end = len(source)

        header = source[:header_end]
        body = source[header_end:]
        new_header = re.sub(r"\bpayable\b\s*", "", header, count=1)
        replacement = new_header + body
        if replacement == source:
            return

        self._add(
            node=node,
            original=source,
            replacement=replacement,
            description="Remove payable",
        )
