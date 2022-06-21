from __future__ import annotations

from typing import List, Optional, Tuple

from woke.ast.ir.abc import IrAbc
from woke.ast.ir.statement.abc import StatementAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcBlock


class Block(StatementAbc):
    _ast_node: SolcBlock
    _parent: IrAbc  # TODO: make this more specific

    __documentation: Optional[str]
    __statements: Optional[List[StatementAbc]]

    def __init__(self, init: IrInitTuple, block: SolcBlock, parent: IrAbc):
        super().__init__(init, block, parent)
        self.__documentation = block.documentation

        if block.statements is None:
            self.__statements = None
        else:
            self.__statements = []
            for statement in block.statements:
                self.__statements.append(StatementAbc.from_ast(init, statement, self))

    @property
    def parent(self) -> IrAbc:
        return self._parent

    @property
    def documentation(self) -> Optional[str]:
        return self.__documentation

    @property
    def statements(self) -> Optional[Tuple[StatementAbc]]:
        if self.__statements is None:
            return None
        return tuple(self.__statements)
