from __future__ import annotations

from functools import lru_cache, reduce
from operator import or_
from typing import TYPE_CHECKING, Iterator, List, Set, Tuple, Union

from woke.ast.enums import ModifiesStateFlag
from woke.ast.ir.abc import IrAbc, SolidityAbc
from woke.ast.ir.expression.function_call import FunctionCall
from woke.ast.ir.meta.try_catch_clause import TryCatchClause
from woke.ast.ir.statement.abc import StatementAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcTryStatement

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
    _parent: Union[
        Block,
        DoWhileStatement,
        ForStatement,
        IfStatement,
        UncheckedBlock,
        WhileStatement,
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
        return self._parent

    @property
    def clauses(self) -> Tuple[TryCatchClause]:
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

    @property
    @lru_cache(maxsize=2048)
    def modifies_state(self) -> Set[Tuple[IrAbc, ModifiesStateFlag]]:
        return (
            reduce(
                or_,
                (clause.modifies_state for clause in self._clauses),
                set(),
            )
            | self.external_call.modifies_state
        )

    def statements_iter(self) -> Iterator["StatementAbc"]:
        yield self
        for clause in self._clauses:
            yield from clause.block.statements_iter()
