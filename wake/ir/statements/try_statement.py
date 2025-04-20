from __future__ import annotations

import weakref
from typing import TYPE_CHECKING, Iterator, List, Tuple, Union

from wake.ir.abc import IrAbc, SolidityAbc
from wake.ir.ast import SolcTryStatement
from wake.ir.expressions.function_call import FunctionCall
from wake.ir.meta.try_catch_clause import TryCatchClause
from wake.ir.statements.abc import StatementAbc
from wake.ir.utils import IrInitTuple

if TYPE_CHECKING:
    from .block import Block
    from .do_while_statement import DoWhileStatement
    from .for_statement import ForStatement
    from .if_statement import IfStatement
    from .unchecked_block import UncheckedBlock
    from .while_statement import WhileStatement


class TryStatement(StatementAbc):
    """
    !!! example
        ```solidity
        try this.f() returns (uint256) {
            // ...
        } catch Error(string memory reason) {
            // ...
        } catch Panic(uint errorCode) {
            // ...
        } catch (bytes memory lowLevelData) {
            // ...
        }
        ```
    """

    _ast_node: SolcTryStatement
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

    _clauses: List[TryCatchClause]
    _external_call: FunctionCall

    def __init__(
        self, init: IrInitTuple, try_statement: SolcTryStatement, parent: SolidityAbc
    ):
        super().__init__(init, try_statement, parent)
        self._clauses = [
            TryCatchClause(init, clause, self) for clause in try_statement.clauses
        ]
        self._external_call = FunctionCall(init, try_statement.external_call, self)

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        for clause in self._clauses:
            yield from clause
        yield from self._external_call

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
    def children(self) -> Iterator[Union[TryCatchClause, FunctionCall]]:
        """
        Yields:
            Direct children of this node.
        """
        yield from self._clauses
        yield self._external_call

    @property
    def clauses(self) -> Tuple[TryCatchClause, ...]:
        """
        Returns:
            Try/catch clauses.
        """
        return tuple(self._clauses)

    @property
    def external_call(self) -> FunctionCall:
        """
        Returns:
            External call executed in the try statement.
        """
        return self._external_call

    def statements_iter(self) -> Iterator[StatementAbc]:
        yield self
        for clause in self._clauses:
            yield from clause.block.statements_iter()
