from __future__ import annotations

from typing import TYPE_CHECKING, Set, Tuple, Union

from woke.ir.abc import IrAbc, SolidityAbc
from woke.ir.ast import SolcBreak
from woke.ir.enums import ModifiesStateFlag
from woke.ir.statements.abc import StatementAbc
from woke.ir.utils import IrInitTuple

if TYPE_CHECKING:
    from .block import Block
    from .do_while_statement import DoWhileStatement
    from .for_statement import ForStatement
    from .if_statement import IfStatement
    from .unchecked_block import UncheckedBlock
    from .while_statement import WhileStatement


class Break(StatementAbc):
    """
    !!! example
        `:::solidity break` in the following code:
        ```solidity
        function foo() public {
            for (uint i = 0; i < 10; i++) {
                if (i == 5)
                    break;
            }
        }
        ```
    """

    _ast_node: SolcBreak
    _parent: Union[
        Block,
        DoWhileStatement,
        ForStatement,
        IfStatement,
        UncheckedBlock,
        WhileStatement,
    ]

    def __init__(self, init: IrInitTuple, break_: SolcBreak, parent: SolidityAbc):
        super().__init__(init, break_, parent)

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
    def modifies_state(self) -> Set[Tuple[IrAbc, ModifiesStateFlag]]:
        return set()
