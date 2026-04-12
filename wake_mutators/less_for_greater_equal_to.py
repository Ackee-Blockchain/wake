from wake.mutators.binary_operator_mutator import BinaryOperatorMutator
from wake.ir.enums import BinaryOpOperator


class LessForGreaterEqualTo(BinaryOperatorMutator):
    """Replace less than (<) with greater than or equal to (>=)"""
    
    name = "less_for_greater_equal_to"
    description = "Replace less than (<) with greater than or equal to (>=)"
    
    operator_map = {
        BinaryOpOperator.LT: BinaryOpOperator.GTE,
    }
