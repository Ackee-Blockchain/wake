from __future__ import annotations

from typing import TYPE_CHECKING, Iterator, Set, Tuple, Union

from wake.ir.ast import SolcYulExpressionStatement, SolcYulFunctionCall
from wake.ir.utils import IrInitTuple

from ..enums import ModifiesStateFlag
from .abc import YulAbc, YulStatementAbc
from .function_call import YulFunctionCall

if TYPE_CHECKING:
    from ..expressions.abc import ExpressionAbc
    from ..statements.abc import StatementAbc
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

    _parent: YulBlock
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
        return self._parent

    @property
    def expression(self) -> YulFunctionCall:
        """
        Returns:
            Underlying expression.
        """
        return self._expression

    @property
    def modifies_state(
        self,
    ) -> Set[Tuple[Union[ExpressionAbc, StatementAbc, YulAbc], ModifiesStateFlag]]:
        return self._expression.modifies_state
