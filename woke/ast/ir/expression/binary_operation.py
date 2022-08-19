from functools import lru_cache
from typing import Iterator

from woke.ast.enums import BinaryOpOperator, ModifiesStateFlag
from woke.ast.ir.abc import IrAbc, SolidityAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcBinaryOperation

from .abc import ExpressionAbc


class BinaryOperation(ExpressionAbc):
    _ast_node: SolcBinaryOperation
    _parent: SolidityAbc  # TODO: make this more specific

    __left_expression: ExpressionAbc
    __operator: BinaryOpOperator
    __right_expression: ExpressionAbc

    def __init__(
        self,
        init: IrInitTuple,
        binary_operation: SolcBinaryOperation,
        parent: SolidityAbc,
    ):
        super().__init__(init, binary_operation, parent)
        self.__operator = binary_operation.operator
        self.__left_expression = ExpressionAbc.from_ast(
            init, binary_operation.left_expression, self
        )
        self.__right_expression = ExpressionAbc.from_ast(
            init, binary_operation.right_expression, self
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
    def is_ref_to_state_variable(self) -> bool:
        return False

    @property
    @lru_cache(maxsize=None)
    def modifies_state(self) -> ModifiesStateFlag:
        return (
            self.left_expression.modifies_state | self.right_expression.modifies_state
        )
