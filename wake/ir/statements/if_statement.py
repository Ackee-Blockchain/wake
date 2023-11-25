from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Iterator, Optional, Set, Tuple, Union

from wake.ir.abc import IrAbc, SolidityAbc
from wake.ir.ast import SolcIfStatement
from wake.ir.enums import ModifiesStateFlag
from wake.ir.expressions.abc import ExpressionAbc
from wake.ir.statements.abc import StatementAbc
from wake.ir.utils import IrInitTuple

if TYPE_CHECKING:
    from ..yul.abc import YulAbc
    from .block import Block
    from .do_while_statement import DoWhileStatement
    from .for_statement import ForStatement
    from .unchecked_block import UncheckedBlock
    from .while_statement import WhileStatement


class IfStatement(StatementAbc):
    """
    !!! example
        Lines 2-6 in the following code:
        ```solidity linenums="1"
        function foo(int x) public pure returns(uint) {
            if (x < 0) {
                return 0;
            } else {
                return uint(x);
            }
        }
        ```
    """

    _ast_node: SolcIfStatement
    _parent: Union[
        Block,
        DoWhileStatement,
        ForStatement,
        IfStatement,
        UncheckedBlock,
        WhileStatement,
    ]

    _condition: ExpressionAbc
    _true_body: StatementAbc
    _false_body: Optional[StatementAbc]

    def __init__(
        self, init: IrInitTuple, if_statement: SolcIfStatement, parent: SolidityAbc
    ):
        super().__init__(init, if_statement, parent)
        self._condition = ExpressionAbc.from_ast(init, if_statement.condition, self)
        self._true_body = StatementAbc.from_ast(init, if_statement.true_body, self)
        self._false_body = (
            None
            if if_statement.false_body is None
            else StatementAbc.from_ast(init, if_statement.false_body, self)
        )

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        yield from self._condition
        yield from self._true_body
        if self._false_body is not None:
            yield from self._false_body

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
    def condition(self) -> ExpressionAbc:
        """
        Returns:
            Condition of the if statement.
        """
        return self._condition

    @property
    def true_body(self) -> StatementAbc:
        """
        Returns:
            Statement executed if the condition is true.
        """
        return self._true_body

    @property
    def false_body(self) -> Optional[StatementAbc]:
        """
        Returns:
            Statement executed if the condition is false (if any).
        """
        return self._false_body

    @property
    @lru_cache(maxsize=2048)
    def modifies_state(
        self,
    ) -> Set[Tuple[Union[ExpressionAbc, StatementAbc, YulAbc], ModifiesStateFlag]]:
        return (
            self.condition.modifies_state
            | self.true_body.modifies_state
            | (self.false_body.modifies_state if self.false_body is not None else set())
        )

    def statements_iter(self) -> Iterator[StatementAbc]:
        yield self
        yield from self._true_body.statements_iter()
        if self._false_body is not None:
            yield from self._false_body.statements_iter()
