from abc import abstractmethod
from typing import Dict, List, Tuple, Union

from wake.mutators.api import Mutator
from wake.ir.expressions.binary_operation import BinaryOperation
from wake.ir.enums import BinaryOpOperator


class BinaryOperatorMutator(Mutator):
    """Base class for binary operator replacement mutators."""

    operator_map: Dict[BinaryOpOperator, Union[BinaryOpOperator, List[BinaryOpOperator]]] = {}
    
    def visit_binary_operation(self, node: BinaryOperation):
        if node.operator not in self.operator_map:
            return
        
        replacements = self.operator_map[node.operator]
        if not isinstance(replacements, list):
            replacements = [replacements]
        
        left = node.left_expression.source
        right = node.right_expression.source
        
        for replacement_op in replacements:
            self._add(
                node=node,
                original=node.source,
                replacement=f"{left} {replacement_op.value} {right}",
            )