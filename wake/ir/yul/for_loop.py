from __future__ import annotations

from typing import TYPE_CHECKING, Iterator, Set, Tuple, Union

from wake.ir.ast import (
    SolcYulForLoop,
    SolcYulFunctionCall,
    SolcYulIdentifier,
    SolcYulLiteral,
)

from ..enums import ModifiesStateFlag
from ..utils import IrInitTuple
from .abc import YulAbc, YulStatementAbc
from .block import YulBlock
from .function_call import YulFunctionCall
from .identifier import YulIdentifier
from .literal import YulLiteral

if TYPE_CHECKING:
    from ..expressions.abc import ExpressionAbc
    from ..statements.abc import StatementAbc


class YulForLoop(YulStatementAbc):
    """
    Represents a for loop with the following structure:

    ```solidity
    for <pre> <condition> <post> {
        <body>
    }
    ```

    !!! example
        ```solidity
        assembly {
            for { let i := 0 } lt(i, 10) { i := add(i, 1) } {
                // ...
            }
        }
        ```
    """

    _parent: YulBlock
    _body: YulBlock
    _condition: Union[YulFunctionCall, YulIdentifier, YulLiteral]
    _post: YulBlock
    _pre: YulBlock

    def __init__(self, init: IrInitTuple, for_loop: SolcYulForLoop, parent: YulAbc):
        super().__init__(init, for_loop, parent)
        self._body = YulBlock(init, for_loop.body, self)
        if isinstance(for_loop.condition, SolcYulFunctionCall):
            self._condition = YulFunctionCall(init, for_loop.condition, self)
        elif isinstance(for_loop.condition, SolcYulIdentifier):
            self._condition = YulIdentifier(init, for_loop.condition, self)
        elif isinstance(for_loop.condition, SolcYulLiteral):
            self._condition = YulLiteral(init, for_loop.condition, self)
        else:
            assert False, f"Unexpected type: {type(for_loop.condition)}"
        self._post = YulBlock(init, for_loop.post, self)
        self._pre = YulBlock(init, for_loop.pre, self)

    def __iter__(self) -> Iterator[YulAbc]:
        yield self
        yield from self._pre
        yield from self._condition
        yield from self._body
        yield from self._post

    @property
    def parent(self) -> YulBlock:
        """
        Returns:
            Parent IR node.
        """
        return self._parent

    @property
    def body(self) -> YulBlock:
        return self._body

    @property
    def condition(self) -> Union[YulFunctionCall, YulIdentifier, YulLiteral]:
        """
        Returns:
            Condition expression that is evaluated before each iteration.
        """
        return self._condition

    @property
    def post(self) -> YulBlock:
        """
        Returns:
            Block of statements that are executed after each iteration.
        """
        return self._post

    @property
    def pre(self) -> YulBlock:
        """
        Returns:
            Block of statements that are executed once before the first iteration.
        """
        return self._pre

    @property
    def modifies_state(
        self,
    ) -> Set[Tuple[Union[ExpressionAbc, StatementAbc, YulAbc], ModifiesStateFlag]]:
        return (
            self._pre.modifies_state
            | self._condition.modifies_state
            | self._post.modifies_state
            | self._body.modifies_state
        )
