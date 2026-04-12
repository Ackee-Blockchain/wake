from wake.mutators.binary_operator_mutator import BinaryOperatorMutator
from wake.ir.enums import BinaryOpOperator


class AndForOrReplacement(BinaryOperatorMutator):
    """Replace && with ||"""
    
    name = "and_for_or"
    description = "Replace && with ||"
    
    operator_map = {
        BinaryOpOperator.BOOLEAN_AND: BinaryOpOperator.BOOLEAN_OR,
    }
