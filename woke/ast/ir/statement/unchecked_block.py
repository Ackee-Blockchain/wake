from typing import List, Optional, Tuple

from woke.ast.ir.abc import IrAbc
from woke.ast.ir.statement.abc import StatementAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcUncheckedBlock


class UncheckedBlock(StatementAbc):
    _ast_node: SolcUncheckedBlock
    _parent: IrAbc  # TODO: make this more specific

    __statements: List[StatementAbc]
    __documentation: Optional[str]

    def __init__(
        self, init: IrInitTuple, unchecked_block: SolcUncheckedBlock, parent: IrAbc
    ):
        super().__init__(init, unchecked_block, parent)
        self.__statements = [
            StatementAbc.from_ast(init, statement, self)
            for statement in unchecked_block.statements
        ]
        self.__documentation = unchecked_block.documentation

    @property
    def parent(self) -> IrAbc:
        return self._parent

    @property
    def statements(self) -> Tuple[StatementAbc]:
        return tuple(self.__statements)

    @property
    def documentation(self) -> Optional[str]:
        return self.__documentation
