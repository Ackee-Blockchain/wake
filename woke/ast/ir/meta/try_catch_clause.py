from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from ..statement.block import Block
from ..utils import IrInitTuple
from .parameter_list import ParameterList

if TYPE_CHECKING:
    from ..statement.try_statement import TryStatement

from woke.ast.ir.abc import IrAbc
from woke.ast.nodes import SolcTryCatchClause


class TryCatchClause(IrAbc):
    _ast_node: SolcTryCatchClause
    _parent: TryStatement

    __block: Block
    __error_name: str
    __parameters: Optional[ParameterList]

    def __init__(
        self,
        init: IrInitTuple,
        try_catch_clause: SolcTryCatchClause,
        parent: TryStatement,
    ):
        super().__init__(init, try_catch_clause, parent)
        self.__block = Block(init, try_catch_clause.block, self)
        self.__error_name = try_catch_clause.error_name

        if try_catch_clause.parameters is None:
            self.__parameters = None
        else:
            self.__parameters = ParameterList(init, try_catch_clause.parameters, self)

    @property
    def parent(self) -> TryStatement:
        return self._parent

    @property
    def block(self) -> Block:
        return self.__block

    @property
    def error_name(self) -> str:
        return self.__error_name

    @property
    def parameters(self) -> Optional[ParameterList]:
        return self.__parameters
