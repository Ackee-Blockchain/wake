from wake.mutators.binary_operator_mutator import BinaryOperatorMutator
from wake.ir.enums import BinaryOpOperator


class OrForAndReplacement(BinaryOperatorMutator):
    """Replace || with &&"""
    
    name = "or_for_and"
    description = "Replace || with &&"
    
    operator_map = {
        BinaryOpOperator.BOOLEAN_OR: BinaryOpOperator.BOOLEAN_AND,
    }