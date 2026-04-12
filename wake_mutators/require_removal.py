from wake.mutators.api import Mutator
from wake.ir.statements.revert_statement import RevertStatement
from wake.ir.expressions.function_call import FunctionCall

class RequireRemoval(Mutator):
    """Remove require statements"""
    
    name = "require_removal" 
    description = "Remove require/assert statements"
    
    def visit_function_call(self, node: FunctionCall):
        name = None
        if hasattr(node, 'function_name'):
            name = node.function_name
        elif hasattr(node.expression, 'name'):
            name = node.expression.name
            
        if name in ("require", "assert"):
            self._add(
                node=node,
                original=node.source,
                replacement="true",
                description=f"Remove {name}",
            )