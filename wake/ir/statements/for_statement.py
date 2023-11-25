from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Iterator, Optional, Set, Tuple, Union

from wake.ir.abc import IrAbc, SolidityAbc
from wake.ir.ast import (
    SolcExpressionStatement,
    SolcForStatement,
    SolcVariableDeclarationStatement,
)
from wake.ir.enums import ModifiesStateFlag
from wake.ir.expressions.abc import ExpressionAbc
from wake.ir.statements.abc import StatementAbc
from wake.ir.statements.expression_statement import ExpressionStatement
from wake.ir.statements.variable_declaration_statement import (
    VariableDeclarationStatement,
)
from wake.ir.utils import IrInitTuple

if TYPE_CHECKING:
    from ..yul.abc import YulAbc
    from .block import Block
    from .do_while_statement import DoWhileStatement
    from .if_statement import IfStatement
    from .unchecked_block import UncheckedBlock
    from .while_statement import WhileStatement


class ForStatement(StatementAbc):
    """
    !!! example
        Lines 2-4 in the following code:
        ```solidity linenums="1"
        function foo(uint x) public pure {
            for (uint i = 0; i < 10; i++) {
                x += 1;
            }
        }
        ```
    """

    _ast_node: SolcForStatement
    _parent: Union[
        Block,
        DoWhileStatement,
        ForStatement,
        IfStatement,
        UncheckedBlock,
        WhileStatement,
    ]

    _body: StatementAbc
    _condition: Optional[ExpressionAbc]
    _initialization_expression: Optional[
        Union[ExpressionStatement, VariableDeclarationStatement]
    ]
    _loop_expression: Optional[ExpressionStatement]

    def __init__(self, init: IrInitTuple, for_: SolcForStatement, parent: SolidityAbc):
        super().__init__(init, for_, parent)
        self._body = StatementAbc.from_ast(init, for_.body, self)

        self._condition = (
            ExpressionAbc.from_ast(init, for_.condition, self)
            if for_.condition
            else None
        )

        if for_.initialization_expression is None:
            self._initialization_expression = None
        else:
            if isinstance(for_.initialization_expression, SolcExpressionStatement):
                self._initialization_expression = ExpressionStatement(
                    init, for_.initialization_expression, self
                )
            elif isinstance(
                for_.initialization_expression, SolcVariableDeclarationStatement
            ):
                self._initialization_expression = VariableDeclarationStatement(
                    init, for_.initialization_expression, self
                )

        self._loop_expression = (
            ExpressionStatement(init, for_.loop_expression, self)
            if for_.loop_expression
            else None
        )

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        yield from self._body
        if self._condition is not None:
            yield from self._condition
        if self._initialization_expression is not None:
            yield from self._initialization_expression
        if self._loop_expression is not None:
            yield from self._loop_expression

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
            Body of the for loop.
        """
        return self._body

    @property
    def condition(self) -> Optional[ExpressionAbc]:
        """
        !!! example
            ```solidity
            i < 10
            ```
            in the following for loop:
            ```solidity
            for (uint i = 0; i < 10; i++) {}
            ```

        Returns:
            Condition of the for loop, if any.
        """
        return self._condition

    @property
    def initialization_expression(
        self,
    ) -> Optional[Union[ExpressionStatement, VariableDeclarationStatement]]:
        """
        !!! example
            ```solidity
            uint i = 0
            ```
            in the following for loop:
            ```solidity
            for (uint i = 0; i < 10; i++) {}
            ```

        Returns:
            Initialization expression of the for loop, if any.
        """
        return self._initialization_expression

    @property
    def loop_expression(self) -> Optional[ExpressionStatement]:
        """
        !!! example
            ```solidity
            i++
            ```
            in the following for loop:
            ```solidity
            for (uint i = 0; i < 10; i++) {}
            ```

        Returns:
            Loop expression of the for loop, if any.
        """
        return self._loop_expression

    @property
    @lru_cache(maxsize=2048)
    def modifies_state(
        self,
    ) -> Set[Tuple[Union[ExpressionAbc, StatementAbc, YulAbc], ModifiesStateFlag]]:
        ret = set()
        if self.initialization_expression is not None:
            ret |= self.initialization_expression.modifies_state
        if self.condition is not None:
            ret |= self.condition.modifies_state
        if self.loop_expression is not None:
            ret |= self.loop_expression.modifies_state
        return ret

    def statements_iter(self) -> Iterator[StatementAbc]:
        yield self
        yield from self._body.statements_iter()
        if self._initialization_expression is not None:
            yield from self._initialization_expression.statements_iter()
        if self._loop_expression is not None:
            yield from self._loop_expression.statements_iter()
