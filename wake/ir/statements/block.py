from __future__ import annotations

import weakref
from typing import TYPE_CHECKING, Iterator, List, Tuple, Union

from wake.ir.abc import IrAbc, SolidityAbc
from wake.ir.ast import SolcBlock
from wake.ir.statements.abc import StatementAbc
from wake.ir.utils import IrInitTuple

if TYPE_CHECKING:
    from ..declarations.function_definition import FunctionDefinition
    from ..declarations.modifier_definition import ModifierDefinition
    from ..meta.try_catch_clause import TryCatchClause
    from .do_while_statement import DoWhileStatement
    from .for_statement import ForStatement
    from .if_statement import IfStatement
    from .unchecked_block import UncheckedBlock
    from .while_statement import WhileStatement


class Block(StatementAbc):
    """
    Block statements group multiple statements into a single block.

    !!! example
        Lines 3-5 in the following code:
        ```solidity linenums="1"
        contract Foo {
            function bar(uint a, uint b) public pure returns(uint)
            {
                return a + b;
            }
        }
        ```
    """

    _ast_node: SolcBlock
    _parent: weakref.ReferenceType[
        Union[
            Block,
            DoWhileStatement,
            ForStatement,
            IfStatement,
            UncheckedBlock,
            WhileStatement,  # statements
            FunctionDefinition,
            ModifierDefinition,  # declarations
            TryCatchClause,  # meta
        ]
    ]

    _statements: List[StatementAbc]

    def __init__(self, init: IrInitTuple, block: SolcBlock, parent: SolidityAbc):
        super().__init__(init, block, parent)
        self._statements = [
            StatementAbc.from_ast(init, statement, self)
            for statement in block.statements
        ]

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        if self._statements is not None:
            for statement in self._statements:
                yield from statement

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
        FunctionDefinition,
        ModifierDefinition,
        TryCatchClause,
    ]:
        """
        Returns:
            Parent IR node.
        """
        return super().parent

    @property
    def children(self) -> Iterator[StatementAbc]:
        """
        Yields:
            Direct children of this node.
        """
        yield from self._statements

    @property
    def statements(self) -> Tuple[StatementAbc, ...]:
        """
        Can be empty.

        Returns:
            Statements in the block.
        """
        return tuple(self._statements)

    def statements_iter(self) -> Iterator[StatementAbc]:
        yield self
        if self._statements is not None:
            for statement in self._statements:
                yield from statement.statements_iter()
