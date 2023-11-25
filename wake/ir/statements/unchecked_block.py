from __future__ import annotations

from functools import lru_cache, reduce
from operator import or_
from typing import TYPE_CHECKING, Iterator, List, Set, Tuple, Union

from wake.ir.abc import IrAbc, SolidityAbc
from wake.ir.ast import SolcUncheckedBlock
from wake.ir.enums import ModifiesStateFlag
from wake.ir.statements.abc import StatementAbc
from wake.ir.utils import IrInitTuple

if TYPE_CHECKING:
    from ..expressions.abc import ExpressionAbc
    from ..yul.abc import YulAbc
    from .block import Block
    from .do_while_statement import DoWhileStatement
    from .for_statement import ForStatement
    from .if_statement import IfStatement
    from .while_statement import WhileStatement


class UncheckedBlock(StatementAbc):
    """
    !!! example
        Lines 2-4 in the following code:
        ```solidity linenums="1"
        function inc(uint x) public pure returns(uint) {
            unchecked {
                x += 1;
            }
            return x;
        }
        ```
    """

    _ast_node: SolcUncheckedBlock
    _parent: Union[Block, DoWhileStatement, ForStatement, IfStatement, WhileStatement]

    _statements: List[StatementAbc]

    def __init__(
        self,
        init: IrInitTuple,
        unchecked_block: SolcUncheckedBlock,
        parent: SolidityAbc,
    ):
        super().__init__(init, unchecked_block, parent)
        self._statements = [
            StatementAbc.from_ast(init, statement, self)
            for statement in unchecked_block.statements
        ]

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        for statement in self._statements:
            yield from statement

    @property
    def parent(
        self,
    ) -> Union[Block, DoWhileStatement, ForStatement, IfStatement, WhileStatement]:
        """
        Returns:
            Parent IR node.
        """
        return self._parent

    @property
    def statements(self) -> Tuple[StatementAbc, ...]:
        """
        Can be empty.

        Returns:
            Statements in the block.
        """
        return tuple(self._statements)

    @property
    @lru_cache(maxsize=2048)
    def modifies_state(
        self,
    ) -> Set[Tuple[Union[ExpressionAbc, StatementAbc, YulAbc], ModifiesStateFlag]]:
        return reduce(
            or_,
            (statement.modifies_state for statement in self._statements),
            set(),
        )

    def statements_iter(self) -> Iterator[StatementAbc]:
        yield self
        for statement in self._statements:
            yield from statement.statements_iter()
