from wake.mutators.binary_operator_mutator import BinaryOperatorMutator
from wake.ir.enums import BinaryOpOperator


class MinusForPlusReplacement(BinaryOperatorMutator):
    """Replace subtraction (-) with addition (+)"""
    
    name = "minus_for_plus"
    description = "Replace subtraction (-) with addition (+)"
    
    operator_map = {
        BinaryOpOperator.MINUS: BinaryOpOperator.PLUS,
    }