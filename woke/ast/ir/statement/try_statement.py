from typing import Iterator, List, Optional, Tuple

from woke.ast.ir.abc import IrAbc, SolidityAbc
from woke.ast.ir.expression.function_call import FunctionCall
from woke.ast.ir.meta.try_catch_clause import TryCatchClause
from woke.ast.ir.statement.abc import StatementAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcTryStatement


class TryStatement(StatementAbc):
    _ast_node: SolcTryStatement
    _parent: SolidityAbc  # TODO: make this more specific

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
    def parent(self) -> SolidityAbc:
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
