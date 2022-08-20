from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Union

from woke.ast.enums import ModifiesStateFlag
from woke.ast.ir.abc import SolidityAbc
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
    _ast_node: SolcPlaceholderStatement
    _parent: Union[Block, DoWhileStatement, ForStatement, IfStatement, WhileStatement]

    __documentation: Optional[str]

    def __init__(
        self,
        init: IrInitTuple,
        placeholder_statement: SolcPlaceholderStatement,
        parent: SolidityAbc,
    ):
        super().__init__(init, placeholder_statement, parent)
        self.__documentation = placeholder_statement.documentation

    @property
    def parent(
        self,
    ) -> Union[Block, DoWhileStatement, ForStatement, IfStatement, WhileStatement]:
        return self._parent

    @property
    def documentation(self) -> Optional[str]:
        return self.__documentation

    @property
    def modifies_state(self) -> ModifiesStateFlag:
        return ModifiesStateFlag(0)
