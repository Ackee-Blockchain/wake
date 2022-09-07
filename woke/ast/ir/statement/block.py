from __future__ import annotations

from functools import lru_cache, reduce
from operator import or_
from typing import TYPE_CHECKING, Iterator, List, Set, Tuple, Union

from woke.ast.enums import ModifiesStateFlag
from woke.ast.ir.abc import IrAbc, SolidityAbc
from woke.ast.ir.statement.abc import StatementAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcBlock

if TYPE_CHECKING:
    from ..declaration.function_definition import FunctionDefinition
    from ..declaration.modifier_definition import ModifierDefinition
    from ..meta.try_catch_clause import TryCatchClause
    from .do_while_statement import DoWhileStatement
    from .for_statement import ForStatement
    from .if_statement import IfStatement
    from .unchecked_block import UncheckedBlock
    from .while_statement import WhileStatement


class Block(StatementAbc):
    _ast_node: SolcBlock
    _parent: Union[
        Block,
        DoWhileStatement,
        ForStatement,
        IfStatement,
        UncheckedBlock,
        WhileStatement,  # statements
        FunctionDefinition,
        ModifierDefinition,  # declarations
        TryCatchClause,  # meta
    ]

    __statements: List[StatementAbc]

    def __init__(self, init: IrInitTuple, block: SolcBlock, parent: SolidityAbc):
        super().__init__(init, block, parent)
        self.__statements = [
            StatementAbc.from_ast(init, statement, self)
            for statement in block.statements
        ]

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        if self.__statements is not None:
            for statement in self.__statements:
                yield from statement

    @property
    def parent(
        self,
    ) -> Union[
        Block,
        DoWhileStatement,
        ForStatement,
        IfStatement,
        UncheckedBlock,
        WhileStatement,
        FunctionDefinition,
        ModifierDefinition,
        TryCatchClause,
    ]:
        return self._parent

    @property
    def statements(self) -> Tuple[StatementAbc]:
        return tuple(self.__statements)

    @property
    @lru_cache(maxsize=None)
    def modifies_state(self) -> Set[Tuple[IrAbc, ModifiesStateFlag]]:
        if self.statements is None:
            return set()
        return reduce(
            or_,
            (statement.modifies_state for statement in self.statements),
            set(),
        )

    def statements_iter(self) -> Iterator["StatementAbc"]:
        yield self
        if self.__statements is not None:
            for statement in self.__statements:
                yield from statement.statements_iter()
