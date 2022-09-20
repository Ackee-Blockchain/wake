from functools import lru_cache
from typing import Iterator, Optional, Set, Tuple

from woke.ast.enums import ModifiesStateFlag
from woke.ast.ir.abc import IrAbc, SolidityAbc
from woke.ast.ir.expression.abc import ExpressionAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcIndexAccess


class IndexAccess(ExpressionAbc):
    """
    TBD
    """

    _ast_node: SolcIndexAccess
    _parent: SolidityAbc  # TODO: make this more specific

    __base_expression: ExpressionAbc
    __index_expression: Optional[ExpressionAbc]

    def __init__(
        self, init: IrInitTuple, index_access: SolcIndexAccess, parent: SolidityAbc
    ):
        super().__init__(init, index_access, parent)
        self.__base_expression = ExpressionAbc.from_ast(
            init, index_access.base_expression, self
        )

        if index_access.index_expression is None:
            self.__index_expression = None
        else:
            self.__index_expression = ExpressionAbc.from_ast(
                init, index_access.index_expression, self
            )

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        yield from self.__base_expression
        if self.__index_expression is not None:
            yield from self.__index_expression

    @property
    def parent(self) -> SolidityAbc:
        return self._parent

    @property
    def base_expression(self) -> ExpressionAbc:
        return self.__base_expression

    @property
    def index_expression(self) -> Optional[ExpressionAbc]:
        return self.__index_expression

    @property
    @lru_cache(maxsize=2048)
    def is_ref_to_state_variable(self) -> bool:
        return self.base_expression.is_ref_to_state_variable

    @property
    @lru_cache(maxsize=2048)
    def modifies_state(self) -> Set[Tuple[IrAbc, ModifiesStateFlag]]:
        ret = self.base_expression.modifies_state
        if self.index_expression is not None:
            ret |= self.index_expression.modifies_state
        return ret
