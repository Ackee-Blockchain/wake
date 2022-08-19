from __future__ import annotations

from functools import lru_cache, reduce
from operator import or_
from typing import Iterator, List, Optional, Tuple

from woke.ast.enums import ModifiesStateFlag
from woke.ast.ir.abc import IrAbc, SolidityAbc
from woke.ast.ir.statement.abc import StatementAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcBlock


class Block(StatementAbc):
    _ast_node: SolcBlock
    _parent: SolidityAbc  # TODO: make this more specific

    __documentation: Optional[str]
    __statements: Optional[List[StatementAbc]]

    def __init__(self, init: IrInitTuple, block: SolcBlock, parent: SolidityAbc):
        super().__init__(init, block, parent)
        self.__documentation = block.documentation

        if block.statements is None:
            self.__statements = None
        else:
            self.__statements = []
            for statement in block.statements:
                self.__statements.append(StatementAbc.from_ast(init, statement, self))

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        if self.__statements is not None:
            for statement in self.__statements:
                yield from statement

    @property
    def parent(self) -> SolidityAbc:
        return self._parent

    @property
    def documentation(self) -> Optional[str]:
        return self.__documentation

    @property
    def statements(self) -> Optional[Tuple[StatementAbc]]:
        if self.__statements is None:
            return None
        return tuple(self.__statements)

    @property
    @lru_cache(maxsize=None)
    def modifies_state(self) -> ModifiesStateFlag:
        if self.statements is None:
            return ModifiesStateFlag(0)
        return reduce(
            or_,
            (statement.modifies_state for statement in self.statements),
            ModifiesStateFlag(0),
        )
