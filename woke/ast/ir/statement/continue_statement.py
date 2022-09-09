from __future__ import annotations

from typing import TYPE_CHECKING, Set, Tuple, Union

from woke.ast.enums import ModifiesStateFlag
from woke.ast.ir.abc import IrAbc, SolidityAbc
from woke.ast.ir.statement.abc import StatementAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcContinue

if TYPE_CHECKING:
    from .block import Block
    from .do_while_statement import DoWhileStatement
    from .for_statement import ForStatement
    from .if_statement import IfStatement
    from .unchecked_block import UncheckedBlock
    from .while_statement import WhileStatement


class Continue(StatementAbc):
    """
    !!! example
        `:::solidity continue` in the following code:
        ```solidity
        function foo() public {
            for (uint i = 0; i < 10; i++) {
                if (i == 5)
                    continue;
            }
        }
        ```
    """
    _ast_node: SolcContinue
    _parent: Union[
        Block,
        DoWhileStatement,
        ForStatement,
        IfStatement,
        UncheckedBlock,
        WhileStatement,
    ]

    def __init__(self, init: IrInitTuple, continue_: SolcContinue, parent: SolidityAbc):
        super().__init__(init, continue_, parent)

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
