from __future__ import annotations

from functools import lru_cache, reduce
from operator import or_
from typing import TYPE_CHECKING, Iterator, List, Set, Tuple, Union

from woke.ast.enums import ModifiesStateFlag
from woke.ast.ir.abc import IrAbc, SolidityAbc
from woke.ast.ir.statement.abc import StatementAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcBlock

if TYPE_CHECKING:
    from ..declaration.function_definition import FunctionDefinition
    from ..declaration.modifier_definition import ModifierDefinition
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
    _parent: Union[
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
        return self._parent

    @property
    def statements(self) -> Tuple[StatementAbc]:
        """
        Can be empty.
        Returns:
            Statements in the block.
        """
        return tuple(self._statements)

    @property
    @lru_cache(maxsize=2048)
    def modifies_state(self) -> Set[Tuple[IrAbc, ModifiesStateFlag]]:
        if self.statements is None:
            return set()
        return reduce(
            or_,
            (statement.modifies_state for statement in self.statements),
            set(),
        )

    def statements_iter(self) -> Iterator["StatementAbc"]:
        yield self
        if self._statements is not None:
            for statement in self._statements:
                yield from statement.statements_iter()
