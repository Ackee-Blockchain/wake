from woke.ast.ir.abc import IrAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcConditional

from .abc import ExpressionAbc


class Conditional(ExpressionAbc):
    _ast_node: SolcConditional
    _parent: IrAbc  # TODO: make this more specific

    __condition: ExpressionAbc
    __false_expression: ExpressionAbc
    __true_expression: ExpressionAbc

    def __init__(self, init: IrInitTuple, conditional: SolcConditional, parent: IrAbc):
        super().__init__(init, conditional, parent)
        self.__condition = ExpressionAbc.from_ast(init, conditional.condition, self)
        self.__false_expression = ExpressionAbc.from_ast(
            init, conditional.false_expression, self
        )
        self.__true_expression = ExpressionAbc.from_ast(
            init, conditional.true_expression, self
        )

    @property
    def parent(self) -> IrAbc:
        return self._parent

    @property
    def condition(self) -> ExpressionAbc:
        return self.__condition

    @property
    def false_expression(self) -> ExpressionAbc:
        return self.__false_expression

    @property
    def true_expression(self) -> ExpressionAbc:
        return self.__true_expression
