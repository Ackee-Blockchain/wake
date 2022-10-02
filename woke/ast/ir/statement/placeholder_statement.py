from __future__ import annotations

from typing import TYPE_CHECKING, Set, Tuple, Union

from woke.ast.enums import ModifiesStateFlag
from woke.ast.ir.abc import IrAbc, SolidityAbc
from woke.ast.ir.statement.abc import StatementAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcPlaceholderStatement

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
    _parent: Union[Block, DoWhileStatement, ForStatement, IfStatement, WhileStatement]

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
        return self._parent

    @property
    def modifies_state(self) -> Set[Tuple[IrAbc, ModifiesStateFlag]]:
        return set()
