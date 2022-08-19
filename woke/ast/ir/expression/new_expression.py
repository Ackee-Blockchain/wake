from typing import Iterator

from woke.ast.ir.abc import IrAbc, SolidityAbc
from woke.ast.ir.expression.abc import ExpressionAbc
from woke.ast.ir.type_name.abc import TypeNameAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcNewExpression


class NewExpression(ExpressionAbc):
    _ast_node: SolcNewExpression
    _parent: SolidityAbc  # TODO: make this more specific

    __type_name: TypeNameAbc

    def __init__(
        self, init: IrInitTuple, new_expression: SolcNewExpression, parent: SolidityAbc
    ):
        super().__init__(init, new_expression, parent)
        self.__type_name = TypeNameAbc.from_ast(init, new_expression.type_name, self)

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        yield from self.__type_name

    @property
    def parent(self) -> SolidityAbc:
        return self._parent

    @property
    def type_name(self) -> TypeNameAbc:
        return self.__type_name

    @property
    def is_ref_to_state_variable(self) -> bool:
        return False
