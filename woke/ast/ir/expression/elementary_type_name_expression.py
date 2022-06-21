from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcElementaryTypeNameExpression

from ..abc import IrAbc
from ..type_name.elementary_type_name import ElementaryTypeName
from .abc import ExpressionAbc


class ElementaryTypeNameExpression(ExpressionAbc):
    _ast_node: SolcElementaryTypeNameExpression
    _parent: IrAbc  # TODO: make this more specific

    __type_name: ElementaryTypeName

    def __init__(
        self,
        init: IrInitTuple,
        elementary_type_name_expression: SolcElementaryTypeNameExpression,
        parent: IrAbc,
    ):
        super().__init__(init, elementary_type_name_expression, parent)
        self.__type_name = ElementaryTypeName(
            init, elementary_type_name_expression.type_name, self
        )

    @property
    def parent(self) -> IrAbc:
        return self._parent

    @property
    def type_name(self) -> ElementaryTypeName:
        return self.__type_name
