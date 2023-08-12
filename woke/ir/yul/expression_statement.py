from __future__ import annotations

from typing import TYPE_CHECKING, Iterator, Union

from woke.ir.ast import (
    SolcYulExpressionStatement,
    SolcYulFunctionCall,
    SolcYulIdentifier,
    SolcYulLiteral,
)
from woke.ir.utils import IrInitTuple

from .abc import YulAbc, YulStatementAbc
from .function_call import YulFunctionCall
from .identifier import YulIdentifier
from .literal import YulLiteral

if TYPE_CHECKING:
    from .block import YulBlock


class YulExpressionStatement(YulStatementAbc):
    """
    TBD
    """

    _parent: YulBlock
    _expression: Union[YulFunctionCall, YulIdentifier, YulLiteral]

    def __init__(
        self,
        init: IrInitTuple,
        expression_statement: SolcYulExpressionStatement,
        parent: YulAbc,
    ):
        super().__init__(init, expression_statement, parent)
        if isinstance(expression_statement.expression, SolcYulFunctionCall):
            self._expression = YulFunctionCall(
                init, expression_statement.expression, self
            )
        elif isinstance(expression_statement.expression, SolcYulIdentifier):
            self._expression = YulIdentifier(
                init, expression_statement.expression, self
            )
        elif isinstance(expression_statement.expression, SolcYulLiteral):
            self._expression = YulLiteral(init, expression_statement.expression, self)
        else:
            assert False, f"Unexpected type: {type(expression_statement.expression)}"

    def __iter__(self) -> Iterator[YulAbc]:
        yield self
        yield from self._expression

    @property
    def parent(self) -> YulBlock:
        return self._parent

    @property
    def expression(self) -> Union[YulFunctionCall, YulIdentifier, YulLiteral]:
        return self._expression
