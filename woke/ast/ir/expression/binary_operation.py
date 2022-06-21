from woke.ast.enums import BinaryOpOperator
from woke.ast.ir.abc import IrAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcBinaryOperation

from .abc import ExpressionAbc


class BinaryOperation(ExpressionAbc):
    _ast_node: SolcBinaryOperation
    _parent: IrAbc  # TODO: make this more specific

    __left_expression: ExpressionAbc
    __operator: BinaryOpOperator
    __right_expression: ExpressionAbc

    def __init__(
        self, init: IrInitTuple, binary_operation: SolcBinaryOperation, parent: IrAbc
    ):
        super().__init__(init, binary_operation, parent)
        self.__operator = binary_operation.operator
        self.__left_expression = ExpressionAbc.from_ast(
            init, binary_operation.left_expression, self
        )
        self.__right_expression = ExpressionAbc.from_ast(
            init, binary_operation.right_expression, self
        )

    @property
    def parent(self) -> IrAbc:
        return self._parent

    @property
    def left_expression(self) -> ExpressionAbc:
        return self.__left_expression

    @property
    def right_expression(self) -> ExpressionAbc:
        return self.__right_expression
