from functools import lru_cache, reduce
from operator import or_
from typing import Iterator, List, Optional, Tuple

from woke.ast.enums import ModifiesStateFlag
from woke.ast.ir.abc import IrAbc, SolidityAbc
from woke.ast.ir.statement.abc import StatementAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcUncheckedBlock


class UncheckedBlock(StatementAbc):
    _ast_node: SolcUncheckedBlock
    _parent: SolidityAbc  # TODO: make this more specific

    __statements: List[StatementAbc]
    __documentation: Optional[str]

    def __init__(
        self,
        init: IrInitTuple,
        unchecked_block: SolcUncheckedBlock,
        parent: SolidityAbc,
    ):
        super().__init__(init, unchecked_block, parent)
        self.__statements = [
            StatementAbc.from_ast(init, statement, self)
            for statement in unchecked_block.statements
        ]
        self.__documentation = unchecked_block.documentation

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        for statement in self.__statements:
            yield from statement

    @property
    def parent(self) -> SolidityAbc:
        return self._parent

    @property
    def statements(self) -> Tuple[StatementAbc]:
        return tuple(self.__statements)

    @property
    def documentation(self) -> Optional[str]:
        return self.__documentation

    @property
    @lru_cache(maxsize=None)
    def modifies_state(self) -> ModifiesStateFlag:
        return reduce(
            or_,
            (statement.modifies_state for statement in self.__statements),
            ModifiesStateFlag(0),
        )
