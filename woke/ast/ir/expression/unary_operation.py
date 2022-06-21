from woke.ast.enums import UnaryOpOperator
from woke.ast.ir.abc import IrAbc
from woke.ast.ir.expression.abc import ExpressionAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcUnaryOperation


class UnaryOperation(ExpressionAbc):
    _ast_node: SolcUnaryOperation
    _parent: IrAbc

    __operator: UnaryOpOperator
    __prefix: bool
    __sub_expression: ExpressionAbc

    def __init__(
        self, init: IrInitTuple, unary_operation: SolcUnaryOperation, parent: IrAbc
    ):
        super().__init__(init, unary_operation, parent)
        self.__operator = unary_operation.operator
        self.__prefix = unary_operation.prefix
        self.__sub_expression = ExpressionAbc.from_ast(
            init, unary_operation.sub_expression, self
        )

    @property
    def parent(self) -> IrAbc:
        return self._parent

    @property
    def operator(self) -> UnaryOpOperator:
        return self.__operator

    @property
    def prefix(self) -> bool:
        return self.__prefix

    @property
    def sub_expression(self) -> ExpressionAbc:
        return self.__sub_expression
