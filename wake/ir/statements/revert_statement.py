from __future__ import annotations

import weakref
from typing import TYPE_CHECKING, Iterator, Union

from wake.ir.abc import IrAbc, SolidityAbc
from wake.ir.ast import SolcRevertStatement
from wake.ir.expressions.function_call import FunctionCall
from wake.ir.statements.abc import StatementAbc
from wake.ir.utils import IrInitTuple

if TYPE_CHECKING:
    from .block import Block
    from .do_while_statement import DoWhileStatement
    from .for_statement import ForStatement
    from .if_statement import IfStatement
    from .unchecked_block import UncheckedBlock
    from .while_statement import WhileStatement


class RevertStatement(StatementAbc):
    """
    !!! warning
        Only matches reverts with user-defined errors:
        ```solidity
        revert InsufficientBalance(want, have);
        ```
        This is an [ExpressionStatement][wake.ir.statements.expression_statement.ExpressionStatement] with a [FunctionCall][wake.ir.expressions.function_call.FunctionCall] expression:
        ```solidity
        revert("Insufficient balance");
        ```
    """

    _ast_node: SolcRevertStatement
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

    _error_call: FunctionCall

    def __init__(
        self, init: IrInitTuple, revert: SolcRevertStatement, parent: SolidityAbc
    ):
        super().__init__(init, revert, parent)
        self._error_call = FunctionCall(init, revert.error_call, self)

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        yield from self._error_call

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
    def children(self) -> Iterator[FunctionCall]:
        """
        Yields:
            Direct children of this node.
        """
        yield self._error_call

    @property
    def error_call(self) -> FunctionCall:
        """
        !!! example
            ```solidity
            InsufficientBalance(want, have)
            ```
            in the following revert statement:
            ```solidity
            revert InsufficientBalance(want, have)
            ```

        Returns:
            Expression representing the error call.
        """
        return self._error_call
