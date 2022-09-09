from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Iterator, Set, Tuple, Union

from woke.ast.enums import ModifiesStateFlag
from woke.ast.ir.abc import IrAbc, SolidityAbc
from woke.ast.ir.expression.abc import ExpressionAbc
from woke.ast.ir.statement.abc import StatementAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcDoWhileStatement

if TYPE_CHECKING:
    from .block import Block
    from .for_statement import ForStatement
    from .if_statement import IfStatement
    from .unchecked_block import UncheckedBlock
    from .while_statement import WhileStatement


class DoWhileStatement(StatementAbc):
    """
    !!! example
        Lines 2-4 in the following code:
        ```solidity linenums="1"
        function foo(uint x) public {
            do {
                x += 1;
            } while (x < 10);
        }
        ```
    """
    _ast_node: SolcDoWhileStatement
    _parent: Union[
        Block,
        DoWhileStatement,
        ForStatement,
        IfStatement,
        UncheckedBlock,
        WhileStatement,
    ]

    __body: StatementAbc
    __condition: ExpressionAbc

    def __init__(
        self, init: IrInitTuple, do_while: SolcDoWhileStatement, parent: SolidityAbc
    ):
        super().__init__(init, do_while, parent)
        self.__body = StatementAbc.from_ast(init, do_while.body, self)
        self.__condition = ExpressionAbc.from_ast(init, do_while.condition, self)

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        yield from self.__body
        yield from self.__condition

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
    def body(self) -> StatementAbc:
        """
        Returns:
            Body of the do-while statement.
        """
        return self.__body

    @property
    def condition(self) -> ExpressionAbc:
        """
        Returns:
            Condition of the do-while statement.
        """
        return self.__condition

    @property
    @lru_cache(maxsize=None)
    def modifies_state(self) -> Set[Tuple[IrAbc, ModifiesStateFlag]]:
        return self.condition.modifies_state | self.body.modifies_state

    def statements_iter(self) -> Iterator["StatementAbc"]:
        yield self
        yield from self.__body.statements_iter()
