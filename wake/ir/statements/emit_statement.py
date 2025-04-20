from __future__ import annotations

import weakref
from typing import TYPE_CHECKING, Iterator, Union

from wake.ir.ast import SolcEmitStatement
from wake.ir.utils import IrInitTuple

from ..abc import IrAbc, SolidityAbc
from ..expressions.function_call import FunctionCall
from ..statements.abc import StatementAbc

if TYPE_CHECKING:
    from ..expressions.abc import ExpressionAbc
    from .block import Block
    from .do_while_statement import DoWhileStatement
    from .for_statement import ForStatement
    from .if_statement import IfStatement
    from .unchecked_block import UncheckedBlock
    from .while_statement import WhileStatement


class EmitStatement(StatementAbc):
    """
    !!! example
        `:::solidity emit Transfer(msg.sender, to, amount)` in the following code:
        ```solidity
        function transfer(address to, uint amount) public {
            emit Transfer(msg.sender, to, amount);
        }
        ```
    """

    _ast_node: SolcEmitStatement
    _parent: weakref.ReferenceType[
        Union[
            Block,
            DoWhileStatement,
            ForStatement,
            IfStatement,
            UncheckedBlock,
            WhileStatement,
        ]
    ]

    _event_call: FunctionCall

    def __init__(self, init: IrInitTuple, emit: SolcEmitStatement, parent: SolidityAbc):
        super().__init__(init, emit, parent)
        self._event_call = FunctionCall(init, emit.event_call, self)

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        yield from self._event_call

    @property
    def parent(
        self,
    ) -> Union[
        Block,
        DoWhileStatement,
        ForStatement,
        IfStatement,
        UncheckedBlock,
        WhileStatement,
    ]:
        """
        Returns:
            Parent IR node.
        """
        return super().parent

    @property
    def children(self) -> Iterator[ExpressionAbc]:
        """
        Yields:
            Direct children of this node.
        """
        yield self._event_call

    @property
    def event_call(self) -> FunctionCall:
        """
        !!! example
            ```solidity
            Transfer(msg.sender, to, amount)
            ```
            in the following emit statement:
            ```solidity
            emit Transfer(msg.sender, to, amount)
            ```

        Returns:
            Expression representing the event call.
        """
        return self._event_call
