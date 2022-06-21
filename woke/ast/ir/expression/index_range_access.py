from typing import Optional

from woke.ast.ir.abc import IrAbc
from woke.ast.ir.expression.abc import ExpressionAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcIndexRangeAccess


class IndexRangeAccess(ExpressionAbc):
    _ast_node: SolcIndexRangeAccess
    _parent: IrAbc  # TODO: make this more specific

    __base_expression: ExpressionAbc
    __start_expression: Optional[ExpressionAbc]
    __end_expression: Optional[ExpressionAbc]

    def __init__(
        self, init: IrInitTuple, index_range_access: SolcIndexRangeAccess, parent: IrAbc
    ):
        super().__init__(init, index_range_access, parent)
        self.__base_expression = ExpressionAbc.from_ast(
            init, index_range_access.base_expression, self
        )

        if index_range_access.start_expression is None:
            self.__start_expression = None
        else:
            self.__start_expression = ExpressionAbc.from_ast(
                init, index_range_access.start_expression, self
            )

        if index_range_access.end_expression is None:
            self.__end_expression = None
        else:
            self.__end_expression = ExpressionAbc.from_ast(
                init, index_range_access.end_expression, self
            )

    @property
    def parent(self) -> IrAbc:
        return self._parent

    @property
    def base_expression(self) -> ExpressionAbc:
        return self.__base_expression

    @property
    def start_expression(self) -> Optional[ExpressionAbc]:
        return self.__start_expression

    @property
    def end_expression(self) -> Optional[ExpressionAbc]:
        return self.__end_expression
