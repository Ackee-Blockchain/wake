from wake.mutators.api import Mutator
from wake.ir.declarations.function_definition import FunctionDefinition


class ModifierDeletion(Mutator):
    """Remove function modifiers one at a time"""
    
    name = "modifier_deletion"
    description = "Delete function modifiers (e.g., onlyOwner)"
    
    def visit_function_definition(self, node: FunctionDefinition):
        if not node.modifiers:
            return
        
        for modifier in node.modifiers:
            mod_source = modifier.source
            
            self._add(
                node=modifier,
                original=mod_source,
                replacement="",
                description=self.description,
            )