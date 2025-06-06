from __future__ import annotations

import weakref
from typing import TYPE_CHECKING, Union

from wake.ir.abc import SolidityAbc
from wake.ir.ast import SolcPlaceholderStatement
from wake.ir.statements.abc import StatementAbc
from wake.ir.utils import IrInitTuple

if TYPE_CHECKING:
    from .block import Block
    from .do_while_statement import DoWhileStatement
    from .for_statement import ForStatement
    from .if_statement import IfStatement
    from .while_statement import WhileStatement


class PlaceholderStatement(StatementAbc):
    """
    Placeholder statements represent `_` (underscore) in a modifier body.
    !!! example
        `:::solidity _` in the following code:
        ```solidity linenums="1"
        modifier foo() {
            require(msg.sender == owner, "Not owner");
            _;
        }
        ```
    """

    _ast_node: SolcPlaceholderStatement
    _parent: weakref.ReferenceType[
        Union[Block, DoWhileStatement, ForStatement, IfStatement, WhileStatement]
    ]

    def __init__(
        self,
        init: IrInitTuple,
        placeholder_statement: SolcPlaceholderStatement,
        parent: SolidityAbc,
    ):
        super().__init__(init, placeholder_statement, parent)

    @property
    def parent(
        self,
    ) -> Union[Block, DoWhileStatement, ForStatement, IfStatement, WhileStatement]:
        """
        Returns:
            Parent IR node.
        """
        return super().parent
