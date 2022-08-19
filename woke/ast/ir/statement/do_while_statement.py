from functools import lru_cache
from typing import Iterator, Optional

from woke.ast.enums import ModifiesStateFlag
from woke.ast.ir.abc import IrAbc, SolidityAbc
from woke.ast.ir.expression.abc import ExpressionAbc
from woke.ast.ir.statement.abc import StatementAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcDoWhileStatement


class DoWhileStatement(StatementAbc):
    _ast_node: SolcDoWhileStatement
    _parent: SolidityAbc  # TODO: make this more specific

    __body: StatementAbc
    __condition: ExpressionAbc
    __documentation: Optional[str]

    def __init__(
        self, init: IrInitTuple, do_while: SolcDoWhileStatement, parent: SolidityAbc
    ):
        super().__init__(init, do_while, parent)
        self.__body = StatementAbc.from_ast(init, do_while.body, self)
        self.__condition = ExpressionAbc.from_ast(init, do_while.condition, self)
        self.__documentation = do_while.documentation

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        yield from self.__body
        yield from self.__condition

    @property
    def parent(self) -> SolidityAbc:
        return self._parent

    @property
    def body(self) -> StatementAbc:
        return self.__body

    @property
    def condition(self) -> ExpressionAbc:
        return self.__condition

    @property
    def documentation(self) -> Optional[str]:
        return self.__documentation

    @property
    @lru_cache(maxsize=None)
    def modifies_state(self) -> ModifiesStateFlag:
        return self.condition.modifies_state | self.body.modifies_state
