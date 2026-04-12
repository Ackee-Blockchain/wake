import re

from wake.mutators.api import Mutator
from wake.ir.declarations.function_definition import FunctionDefinition
from wake.ir.enums import FunctionKind
from wake.ir.enums import Visibility


class ExternalPublicReplacement(Mutator):
    """Replace external with public."""

    name = "external_public_replacement"
    description = "Replace external with public"

    def visit_function_definition(self, node: FunctionDefinition):
        
        if node.kind in [
            FunctionKind.CONSTRUCTOR,
            FunctionKind.RECEIVE, # must be external
            FunctionKind.FALLBACK, # must be external
        ]:
            return
        
        if node.visibility != Visibility.EXTERNAL:
            return

        source = node.source
        header_end = source.find("{")
        if header_end == -1:
            header_end = source.find(";")
        if header_end == -1:
            header_end = len(source)

        header = source[:header_end]
        body = source[header_end:]
        new_header = re.sub(r"\bexternal\b", "public", header, count=1)
        replacement = new_header + body
        if replacement == source:
            return

        self._add(
            node=node,
            original=source,
            replacement=replacement,
            description="Replace external with public",
        )
