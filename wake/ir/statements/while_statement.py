from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Iterator, Set, Tuple, Union

from wake.ir.abc import IrAbc, SolidityAbc
from wake.ir.ast import SolcWhileStatement
from wake.ir.enums import ModifiesStateFlag
from wake.ir.expressions.abc import ExpressionAbc
from wake.ir.statements.abc import StatementAbc
from wake.ir.utils import IrInitTuple

if TYPE_CHECKING:
    from ..yul.abc import YulAbc
    from .block import Block
    from .do_while_statement import DoWhileStatement
    from .for_statement import ForStatement
    from .if_statement import IfStatement
    from .unchecked_block import UncheckedBlock


class WhileStatement(StatementAbc):
    """
    !!! example
        Lines 2-3 in the following code:
        ```solidity linenums="1"
        function foo(uint x) public pure {
            while (x % 2 == 0)
                x /= 2;
        }
        ```
    """

    _ast_node: SolcWhileStatement
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
        self,
        init: IrInitTuple,
        while_statement: SolcWhileStatement,
        parent: SolidityAbc,
    ):
        super().__init__(init, while_statement, parent)
        self._body = StatementAbc.from_ast(init, while_statement.body, self)
        self._condition = ExpressionAbc.from_ast(init, while_statement.condition, self)

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
            Body of the while statement.
        """
        return self._body

    @property
    def condition(self) -> ExpressionAbc:
        """
        Returns:
            Condition of the while statement.
        """
        return self._condition

    @property
    @lru_cache(maxsize=2048)
    def modifies_state(
        self,
    ) -> Set[Tuple[Union[ExpressionAbc, StatementAbc, YulAbc], ModifiesStateFlag]]:
        return self.body.modifies_state | self.condition.modifies_state

    def statements_iter(self) -> Iterator[StatementAbc]:
        yield self
        yield from self._body.statements_iter()
