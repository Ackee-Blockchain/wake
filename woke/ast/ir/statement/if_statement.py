from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Iterator, Optional, Set, Tuple, Union

from woke.ast.enums import ModifiesStateFlag
from woke.ast.ir.abc import IrAbc, SolidityAbc
from woke.ast.ir.expression.abc import ExpressionAbc
from woke.ast.ir.statement.abc import StatementAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcIfStatement

if TYPE_CHECKING:
    from .block import Block
    from .do_while_statement import DoWhileStatement
    from .for_statement import ForStatement
    from .unchecked_block import UncheckedBlock
    from .while_statement import WhileStatement


class IfStatement(StatementAbc):
    _ast_node: SolcIfStatement
    _parent: Union[
        Block,
        DoWhileStatement,
        ForStatement,
        IfStatement,
        UncheckedBlock,
        WhileStatement,
    ]

    __condition: ExpressionAbc
    __true_body: StatementAbc
    __false_body: Optional[StatementAbc]

    def __init__(
        self, init: IrInitTuple, if_statement: SolcIfStatement, parent: SolidityAbc
    ):
        super().__init__(init, if_statement, parent)
        self.__condition = ExpressionAbc.from_ast(init, if_statement.condition, self)
        self.__true_body = StatementAbc.from_ast(init, if_statement.true_body, self)
        self.__false_body = (
            None
            if if_statement.false_body is None
            else StatementAbc.from_ast(init, if_statement.false_body, self)
        )

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        yield from self.__condition
        yield from self.__true_body
        if self.__false_body is not None:
            yield from self.__false_body

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
    def condition(self) -> ExpressionAbc:
        return self.__condition

    @property
    def true_body(self) -> StatementAbc:
        return self.__true_body

    @property
    def false_body(self) -> Optional[StatementAbc]:
        return self.__false_body

    @property
    @lru_cache(maxsize=None)
    def modifies_state(self) -> Set[Tuple[IrAbc, ModifiesStateFlag]]:
        return (
            self.condition.modifies_state
            | self.true_body.modifies_state
            | (self.false_body.modifies_state if self.false_body is not None else set())
        )

    def statements_iter(self) -> Iterator["StatementAbc"]:
        yield self
        yield from self.__true_body.statements_iter()
        if self.__false_body is not None:
            yield from self.__false_body.statements_iter()
