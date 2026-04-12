from abc import abstractmethod
from typing import List

from wake.mutators.api import Mutator
from wake.ir.expressions.literal import Literal
from wake.ir.enums import LiteralKind


class LiteralMutator(Mutator):
    """Base class for literal replacement mutators."""
    
    # Subclasses specify which literal kinds to target
    target_kinds: List[LiteralKind] = []
    
    def visit_literal(self, node: Literal):
        if node.kind not in self.target_kinds:
            return
        
        replacements = self.get_replacements(node)
        
        for replacement in replacements:
            self._add(
                node=node,
                original=node.source,
                replacement=replacement,
            )
    
    @abstractmethod
    def get_replacements(self, node: Literal) -> List[str]:
        """Return list of replacement values for this literal."""
        ...