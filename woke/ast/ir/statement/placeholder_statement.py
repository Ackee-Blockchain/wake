from typing import Optional

from woke.ast.ir.abc import IrAbc
from woke.ast.ir.statement.abc import StatementAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcPlaceholderStatement


class PlaceholderStatement(StatementAbc):
    _ast_node: SolcPlaceholderStatement
    _parent: IrAbc  # TODO: make this more specific

    __documentation: Optional[str]

    def __init__(
        self,
        init: IrInitTuple,
        placeholder_statement: SolcPlaceholderStatement,
        parent: IrAbc,
    ):
        super().__init__(init, placeholder_statement, parent)
        self.__documentation = placeholder_statement.documentation

    @property
    def parent(self) -> IrAbc:
        return self._parent

    @property
    def documentation(self) -> Optional[str]:
        return self.__documentation
