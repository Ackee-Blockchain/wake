from __future__ import annotations

import weakref
from typing import Iterator, Union

from wake.ir.ast import (
    SolcYulFunctionCall,
    SolcYulIdentifier,
    SolcYulIf,
    SolcYulLiteral,
)

from ..utils import IrInitTuple
from .abc import YulAbc, YulStatementAbc
from .block import YulBlock
from .function_call import YulFunctionCall
from .identifier import YulIdentifier
from .literal import YulLiteral


class YulIf(YulStatementAbc):
    """
    Represents an if statement with the following structure:

    ```solidity
    if <condition> {
        <body>
    }
    ```

    !!! example
        ```solidity
        assembly {
            if lt(i, 10) {
                // ...
            }
        }
        ```

    !!! note
        There is no `else` branch in Yul. It must be implemented using a second `if` statement when needed.
    """

    _parent: weakref.ReferenceType[YulBlock]
    _body: YulBlock
    _condition: Union[YulFunctionCall, YulIdentifier, YulLiteral]

    def __init__(self, init: IrInitTuple, if_statement: SolcYulIf, parent: YulAbc):
        super().__init__(init, if_statement, parent)
        self._body = YulBlock(init, if_statement.body, self)
        if isinstance(if_statement.condition, SolcYulFunctionCall):
            self._condition = YulFunctionCall(init, if_statement.condition, self)
        elif isinstance(if_statement.condition, SolcYulIdentifier):
            self._condition = YulIdentifier(init, if_statement.condition, self)
        elif isinstance(if_statement.condition, SolcYulLiteral):
            self._condition = YulLiteral(init, if_statement.condition, self)
        else:
            assert False, f"Unexpected type: {type(if_statement.condition)}"

    def __iter__(self) -> Iterator[YulAbc]:
        yield self
        yield from self._condition
        yield from self._body

    @property
    def parent(self) -> YulBlock:
        """
        Returns:
            Parent IR node.
        """
        return super().parent

    @property
    def children(
        self,
    ) -> Iterator[Union[YulBlock, YulFunctionCall, YulIdentifier, YulLiteral]]:
        """
        Yields:
            Direct children of this node.
        """
        yield self._body
        yield self._condition

    @property
    def body(self) -> YulBlock:
        """
        Returns:
            Body of the function executed if the condition is true.
        """
        return self._body

    @property
    def condition(self) -> Union[YulFunctionCall, YulIdentifier, YulLiteral]:
        """
        Returns:
            Condition of the if statement.
        """
        return self._condition
