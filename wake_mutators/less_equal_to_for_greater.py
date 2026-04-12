from wake.mutators.binary_operator_mutator import BinaryOperatorMutator
from wake.ir.enums import BinaryOpOperator


class LessEqualToForGreater(BinaryOperatorMutator):
    """Replace less than or equal to (<=) with greater than (>)"""
    
    name = "less_equal_to_for_greater"
    description = "Replace less than or equal to (<=) with greater than (>)"
    
    operator_map = {
        BinaryOpOperator.LTE: BinaryOpOperator.GT,
    }
