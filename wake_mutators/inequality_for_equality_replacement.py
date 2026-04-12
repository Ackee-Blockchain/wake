from wake.mutators.binary_operator_mutator import BinaryOperatorMutator
from wake.ir.enums import BinaryOpOperator


class InequalityForEqualityReplacement(BinaryOperatorMutator):
    """Replace inequality (!=) with equality (==)"""
    
    name = "inequality_for_equality"
    description = "Replace inequality (!=) with equality (==)"
    
    operator_map = {
        BinaryOpOperator.NEQ: BinaryOpOperator.EQ,
    }