from functools import lru_cache
from typing import Iterator

from woke.ast.ir.abc import IrAbc, SolidityAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcConditional

from .abc import ExpressionAbc


class Conditional(ExpressionAbc):
    _ast_node: SolcConditional
    _parent: SolidityAbc  # TODO: make this more specific

    __condition: ExpressionAbc
    __false_expression: ExpressionAbc
    __true_expression: ExpressionAbc

    def __init__(
        self, init: IrInitTuple, conditional: SolcConditional, parent: SolidityAbc
    ):
        super().__init__(init, conditional, parent)
        self.__condition = ExpressionAbc.from_ast(init, conditional.condition, self)
        self.__false_expression = ExpressionAbc.from_ast(
            init, conditional.false_expression, self
        )
        self.__true_expression = ExpressionAbc.from_ast(
            init, conditional.true_expression, self
        )

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        yield from self.__condition
        yield from self.__false_expression
        yield from self.__true_expression

    @property
    def parent(self) -> SolidityAbc:
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

    @property
    @lru_cache(maxsize=None)
    def is_ref_to_state_variable(self) -> bool:
        return (
            self.true_expression.is_ref_to_state_variable
            or self.false_expression.is_ref_to_state_variable
        )
