from __future__ import annotations

import weakref
from typing import Iterator

from wake.ir.abc import IrAbc, SolidityAbc
from wake.ir.ast import SolcConditional
from wake.ir.utils import IrInitTuple
from wake.utils.decorators import weak_self_lru_cache

from .abc import ExpressionAbc


class Conditional(ExpressionAbc):
    """
    !!! example
        ```solidity
        x ? y : z
        ```
    """

    _ast_node: SolcConditional
    _parent: weakref.ReferenceType[SolidityAbc]  # TODO: make this more specific

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
        return super().parent

    @property
    def children(self) -> Iterator[ExpressionAbc]:
        """
        Yields:
            Direct children of this node.
        """
        yield self._condition
        yield self._false_expression
        yield self._true_expression

    @property
    def condition(self) -> ExpressionAbc:
        """
        Returns:
            Condition expression.
        """
        return self._condition

    @property
    def false_expression(self) -> ExpressionAbc:
        """
        Returns:
            Expression evaluated when the condition is false.
        """
        return self._false_expression

    @property
    def true_expression(self) -> ExpressionAbc:
        """
        Returns:
            Expression evaluated when the condition is true.
        """
        return self._true_expression

    @property
    @weak_self_lru_cache(maxsize=2048)
    def is_ref_to_state_variable(self) -> bool:
        return (
            self.true_expression.is_ref_to_state_variable
            or self.false_expression.is_ref_to_state_variable
        )
