from wake.mutators.binary_operator_mutator import BinaryOperatorMutator
from wake.ir.enums import BinaryOpOperator


class GreaterOrEqualToForLess(BinaryOperatorMutator):
    """Replace greater than or equal to (>=) with less than (<)"""
    
    name = "greater_or_equal_to_for_less"
    description = "Replace greater than or equal to (>=) with less than (<)"
    
    operator_map = {
        BinaryOpOperator.GTE: BinaryOpOperator.LT,
    }
