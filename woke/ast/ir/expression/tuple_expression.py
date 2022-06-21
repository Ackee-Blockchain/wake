from typing import List, Optional, Tuple

from woke.ast.ir.abc import IrAbc
from woke.ast.ir.expression.abc import ExpressionAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcTupleExpression


class TupleExpression(ExpressionAbc):
    _ast_node: SolcTupleExpression
    _parent: IrAbc  # TODO: make this more specific

    __components: List[Optional[ExpressionAbc]]
    __is_inline_array: bool

    def __init__(
        self, init: IrInitTuple, tuple_expression: SolcTupleExpression, parent: IrAbc
    ):
        super().__init__(init, tuple_expression, parent)
        self.__is_inline_array = tuple_expression.is_inline_array

        self.__components = []
        for component in tuple_expression.components:
            if component is None:
                self.__components.append(None)
            else:
                self.__components.append(ExpressionAbc.from_ast(init, component, self))

    @property
    def parent(self) -> IrAbc:
        return self._parent

    @property
    def is_inline_array(self) -> bool:
        return self.__is_inline_array

    @property
    def components(self) -> Tuple[Optional[ExpressionAbc]]:
        return tuple(self.__components)
