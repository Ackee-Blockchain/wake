from functools import lru_cache
from typing import Iterator, Set, Tuple

from woke.ast.ir.abc import IrAbc, SolidityAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcConditional

from ...enums import ModifiesStateFlag
from .abc import ExpressionAbc


class Conditional(ExpressionAbc):
    """
    TBD
    """

    _ast_node: SolcConditional
    _parent: SolidityAbc  # TODO: make this more specific

    _condition: ExpressionAbc
    _false_expression: ExpressionAbc
    _true_expression: ExpressionAbc

    def __init__(
        self, init: IrInitTuple, conditional: SolcConditional, parent: SolidityAbc
    ):
        super().__init__(init, conditional, parent)
        self._condition = ExpressionAbc.from_ast(init, conditional.condition, self)
        self._false_expression = ExpressionAbc.from_ast(
            init, conditional.false_expression, self
        )
        self._true_expression = ExpressionAbc.from_ast(
            init, conditional.true_expression, self
        )

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        yield from self._condition
        yield from self._false_expression
        yield from self._true_expression

    @property
    def parent(self) -> SolidityAbc:
        return self._parent

    @property
    def condition(self) -> ExpressionAbc:
        return self._condition

    @property
    def false_expression(self) -> ExpressionAbc:
        return self._false_expression

    @property
    def true_expression(self) -> ExpressionAbc:
        return self._true_expression

    @property
    @lru_cache(maxsize=2048)
    def is_ref_to_state_variable(self) -> bool:
        return (
            self.true_expression.is_ref_to_state_variable
            or self.false_expression.is_ref_to_state_variable
        )

    @property
    @lru_cache(maxsize=2048)
    def modifies_state(self) -> Set[Tuple[IrAbc, ModifiesStateFlag]]:
        return (
            self.condition.modifies_state
            | self.true_expression.modifies_state
            | self.false_expression.modifies_state
        )
