from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Iterator, Set, Tuple, Union

from wake.ir.abc import IrAbc, SolidityAbc
from wake.ir.ast import SolcDoWhileStatement
from wake.ir.enums import ModifiesStateFlag
from wake.ir.expressions.abc import ExpressionAbc
from wake.ir.statements.abc import StatementAbc
from wake.ir.utils import IrInitTuple

if TYPE_CHECKING:
    from ..yul.abc import YulAbc
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

    _body: StatementAbc
    _condition: ExpressionAbc

    def __init__(
        self, init: IrInitTuple, do_while: SolcDoWhileStatement, parent: SolidityAbc
    ):
        super().__init__(init, do_while, parent)
        self._body = StatementAbc.from_ast(init, do_while.body, self)
        self._condition = ExpressionAbc.from_ast(init, do_while.condition, self)

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        yield from self._body
        yield from self._condition

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
        return self._body

    @property
    def condition(self) -> ExpressionAbc:
        """
        Returns:
            Condition of the do-while statement.
        """
        return self._condition

    @property
    @lru_cache(maxsize=2048)
    def modifies_state(
        self,
    ) -> Set[Tuple[Union[ExpressionAbc, StatementAbc, YulAbc], ModifiesStateFlag]]:
        return self.condition.modifies_state | self.body.modifies_state

    def statements_iter(self) -> Iterator[StatementAbc]:
        yield self
        yield from self._body.statements_iter()
