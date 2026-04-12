from wake.mutators.binary_operator_mutator import BinaryOperatorMutator
from wake.ir.enums import BinaryOpOperator


class PlusForMinusReplacement(BinaryOperatorMutator):
    """Replace addition (+) with subtraction (-)"""
    
    name = "plus_for_minus"
    description = "Replace addition (+) with subtraction (-)"
    
    operator_map = {
        BinaryOpOperator.PLUS: BinaryOpOperator.MINUS,
    }