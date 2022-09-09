from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Iterator, Set, Tuple, Union

from woke.ast.enums import ModifiesStateFlag
from woke.ast.ir.abc import IrAbc, SolidityAbc
from woke.ast.ir.expression.abc import ExpressionAbc
from woke.ast.ir.statement.abc import StatementAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcWhileStatement

if TYPE_CHECKING:
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

    __body: StatementAbc
    __condition: ExpressionAbc

    def __init__(
        self,
        init: IrInitTuple,
        while_statement: SolcWhileStatement,
        parent: SolidityAbc,
    ):
        super().__init__(init, while_statement, parent)
        self.__body = StatementAbc.from_ast(init, while_statement.body, self)
        self.__condition = ExpressionAbc.from_ast(init, while_statement.condition, self)

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
            Body of the while statement.
        """
        return self.__body

    @property
    def condition(self) -> ExpressionAbc:
        """
        Returns:
            Condition of the while statement.
        """
        return self.__condition

    @property
    @lru_cache(maxsize=None)
    def modifies_state(self) -> Set[Tuple[IrAbc, ModifiesStateFlag]]:
        return self.body.modifies_state | self.condition.modifies_state

    def statements_iter(self) -> Iterator["StatementAbc"]:
        yield self
        yield from self.__body.statements_iter()
