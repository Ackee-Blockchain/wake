from typing import Optional

from woke.ast.ir.abc import IrAbc
from woke.ast.ir.expression.abc import ExpressionAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcIndexAccess


class IndexAccess(ExpressionAbc):
    _ast_node: SolcIndexAccess
    _parent: IrAbc  # TODO: make this more specific

    __base_expression: ExpressionAbc
    __index_expression: Optional[ExpressionAbc]

    def __init__(self, init: IrInitTuple, index_access: SolcIndexAccess, parent: IrAbc):
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

    @property
    def parent(self) -> IrAbc:
        return self._parent

    @property
    def base_expression(self) -> ExpressionAbc:
        return self.__base_expression

    @property
    def index_expression(self) -> Optional[ExpressionAbc]:
        return self.__index_expression
