from wake.mutators.binary_operator_mutator import BinaryOperatorMutator
from wake.ir.enums import BinaryOpOperator


class EqualityForInequalityReplacement(BinaryOperatorMutator):
    """ Replace equality (==) with inequality (!=) """
    
    name = "equality_for_inequality"
    description = "Replace equality (==) with inequality (!=)"
    
    operator_map = {
        BinaryOpOperator.EQ: BinaryOpOperator.NEQ,
    }