from __future__ import annotations

import weakref
from typing import TYPE_CHECKING, Union

from wake.ir.abc import SolidityAbc
from wake.ir.ast import SolcContinue
from wake.ir.statements.abc import StatementAbc
from wake.ir.utils import IrInitTuple

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
    _parent: weakref.ReferenceType[
        Union[
            Block,
            DoWhileStatement,
            ForStatement,
            IfStatement,
            UncheckedBlock,
            WhileStatement,
        ]
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
        return super().parent
