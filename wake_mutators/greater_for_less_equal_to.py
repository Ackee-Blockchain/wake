from wake.mutators.binary_operator_mutator import BinaryOperatorMutator
from wake.ir.enums import BinaryOpOperator


class GreaterForLessEqualTo(BinaryOperatorMutator):
    """Replace greater than (>) with less than or equal to (<=)"""
    
    name = "greater_for_less_equal_to"
    description = "Replace greater than (>) with less than or equal to (<=)"
    
    operator_map = {
        BinaryOpOperator.GT: BinaryOpOperator.LTE,
    }
