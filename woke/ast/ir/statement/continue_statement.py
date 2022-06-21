from typing import Optional

from woke.ast.ir.abc import IrAbc
from woke.ast.ir.statement.abc import StatementAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcContinue


class Continue(StatementAbc):
    _ast_node: SolcContinue
    _parent: IrAbc  # TODO: make this more specific

    __documentation: Optional[str]

    def __init__(self, init: IrInitTuple, continue_: SolcContinue, parent: IrAbc):
        super().__init__(init, continue_, parent)
        self.__documentation = continue_.documentation

    @property
    def parent(self) -> IrAbc:
        return self._parent

    @property
    def documentation(self) -> Optional[str]:
        return self.__documentation
