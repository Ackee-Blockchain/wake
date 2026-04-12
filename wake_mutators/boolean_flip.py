from wake.mutators.literal_mutator import LiteralMutator
from wake.ir.expressions.literal import Literal
from wake.ir.enums import LiteralKind


class BooleanFlipMutator(LiteralMutator):
    """ Flip boolean literals (true, false) """
    
    name = "boolean_literal"
    description = "Flip boolean literals (true, false)"
    
    target_kinds = [LiteralKind.BOOL]
    
    def get_replacements(self, node: Literal) -> list[str]:
        if node.value == "true":
            return ["false"]
        elif node.value == "false":
            return ["true"]
        return []
