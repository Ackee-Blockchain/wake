from typing import Optional

from woke.ast.enums import ModifiesStateFlag
from woke.ast.ir.abc import SolidityAbc
from woke.ast.ir.statement.abc import StatementAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcBreak


class Break(StatementAbc):
    _ast_node: SolcBreak
    _parent: SolidityAbc  # TODO: make this more specific

    __documentation: Optional[str]

    def __init__(self, init: IrInitTuple, break_: SolcBreak, parent: SolidityAbc):
        super().__init__(init, break_, parent)
        self.__documentation = break_.documentation

    @property
    def parent(self) -> SolidityAbc:
        return self._parent

    @property
    def documentation(self) -> Optional[str]:
        return self.__documentation

    @property
    def modifies_state(self) -> ModifiesStateFlag:
        return ModifiesStateFlag(0)
