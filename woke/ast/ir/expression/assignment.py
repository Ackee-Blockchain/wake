from functools import lru_cache
from typing import Iterator

from woke.ast.enums import AssignmentOperator, ModifiesStateFlag
from woke.ast.ir.abc import IrAbc, SolidityAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcAssignment

from .abc import ExpressionAbc


class Assignment(ExpressionAbc):
    _ast_node: SolcAssignment
    _parent: SolidityAbc  # TODO: make this more specific

    __left_expression: ExpressionAbc
    __right_expression: ExpressionAbc
    __operator: AssignmentOperator

    def __init__(
        self, init: IrInitTuple, assignment: SolcAssignment, parent: SolidityAbc
    ):
        super().__init__(init, assignment, parent)
        self.__operator = assignment.operator
        self.__left_expression = ExpressionAbc.from_ast(
            init, assignment.left_hand_side, self
        )
        self.__right_expression = ExpressionAbc.from_ast(
            init, assignment.right_hand_side, self
        )

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        yield from self.__left_expression
        yield from self.__right_expression

    @property
    def parent(self) -> SolidityAbc:
        return self._parent

    @property
    def left_expression(self) -> ExpressionAbc:
        return self.__left_expression

    @property
    def right_expression(self) -> ExpressionAbc:
        return self.__right_expression

    @property
    def operator(self) -> AssignmentOperator:
        return self.__operator

    @property
    @lru_cache(maxsize=None)
    def is_ref_to_state_variable(self) -> bool:
        return self.left_expression.is_ref_to_state_variable

    @property
    @lru_cache(maxsize=None)
    def modifies_state(self) -> ModifiesStateFlag:
        ret = self.left_expression.modifies_state | self.right_expression.modifies_state
        if self.left_expression.is_ref_to_state_variable:
            ret |= ModifiesStateFlag.MODIFIES_STATE_VAR
        return ret
