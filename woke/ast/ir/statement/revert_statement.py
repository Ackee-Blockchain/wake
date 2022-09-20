from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Iterator, Set, Tuple, Union

from woke.ast.enums import ModifiesStateFlag
from woke.ast.ir.abc import IrAbc, SolidityAbc
from woke.ast.ir.expression.function_call import FunctionCall
from woke.ast.ir.statement.abc import StatementAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcRevertStatement

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
        This is an [ExpressionStatement][woke.ast.ir.statement.expression_statement.ExpressionStatement] with a [FunctionCall][woke.ast.ir.expression.function_call.FunctionCall] expression:
        ```solidity
        revert("Insufficient balance");
        ```
    """

    _ast_node: SolcRevertStatement
    _parent: Union[
        Block,
        DoWhileStatement,
        ForStatement,
        IfStatement,
        UncheckedBlock,
        WhileStatement,
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
        return self._parent

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

    @property
    @lru_cache(maxsize=2048)
    def modifies_state(self) -> Set[Tuple[IrAbc, ModifiesStateFlag]]:
        return self.error_call.modifies_state
