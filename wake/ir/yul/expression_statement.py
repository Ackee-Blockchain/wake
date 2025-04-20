from __future__ import annotations

import weakref
from typing import TYPE_CHECKING, Iterator

from wake.ir.ast import SolcYulExpressionStatement, SolcYulFunctionCall
from wake.ir.utils import IrInitTuple

from .abc import YulAbc, YulStatementAbc
from .function_call import YulFunctionCall

if TYPE_CHECKING:
    from .block import YulBlock


class YulExpressionStatement(YulStatementAbc):
    """
    The underlying expression can only be a [YulFunctionCall][wake.ir.yul.function_call.YulFunctionCall].

    !!! example
        ```solidity
        assembly {
            stop()
        }
        ```
    """

    _parent: weakref.ReferenceType[YulBlock]
    _expression: YulFunctionCall

    def __init__(
        self,
        init: IrInitTuple,
        expression_statement: SolcYulExpressionStatement,
        parent: YulAbc,
    ):
        super().__init__(init, expression_statement, parent)
        assert isinstance(
            expression_statement.expression, SolcYulFunctionCall
        ), f"Unexpected type: {type(expression_statement.expression)}"
        self._expression = YulFunctionCall(init, expression_statement.expression, self)

    def __iter__(self) -> Iterator[YulAbc]:
        yield self
        yield from self._expression

    @property
    def parent(self) -> YulBlock:
        """
        Returns:
            Parent IR node.
        """
        return super().parent

    @property
    def children(self) -> Iterator[YulFunctionCall]:
        """
        Yields:
            Direct children of this node.
        """
        yield self._expression

    @property
    def expression(self) -> YulFunctionCall:
        """
        Returns:
            Underlying expression.
        """
        return self._expression
