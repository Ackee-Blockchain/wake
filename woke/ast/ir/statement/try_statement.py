from __future__ import annotations

from functools import lru_cache, reduce
from operator import or_
from typing import TYPE_CHECKING, Iterator, List, Optional, Tuple, Union

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
    _ast_node: SolcTryStatement
    _parent: Union[
        Block,
        DoWhileStatement,
        ForStatement,
        IfStatement,
        UncheckedBlock,
        WhileStatement,
    ]

    __clauses: List[TryCatchClause]
    __external_call: FunctionCall
    __documentation: Optional[str]

    def __init__(
        self, init: IrInitTuple, try_statement: SolcTryStatement, parent: SolidityAbc
    ):
        super().__init__(init, try_statement, parent)
        self.__clauses = [
            TryCatchClause(init, clause, self) for clause in try_statement.clauses
        ]
        self.__external_call = FunctionCall(init, try_statement.external_call, self)
        self.__documentation = try_statement.documentation

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        for clause in self.__clauses:
            yield from clause
        yield from self.__external_call

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
        return self._parent

    @property
    def clauses(self) -> Tuple[TryCatchClause]:
        return tuple(self.__clauses)

    @property
    def external_call(self) -> FunctionCall:
        return self.__external_call

    @property
    def documentation(self) -> Optional[str]:
        return self.__documentation

    @property
    @lru_cache(maxsize=None)
    def modifies_state(self) -> ModifiesStateFlag:
        return (
            reduce(
                or_,
                (clause.block.modifies_state for clause in self.__clauses),
                ModifiesStateFlag(0),
            )
            | self.external_call.modifies_state
        )
