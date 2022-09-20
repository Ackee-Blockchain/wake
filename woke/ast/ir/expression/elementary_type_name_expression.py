from typing import Iterator, Set, Tuple

from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcElementaryTypeNameExpression

from ...enums import ModifiesStateFlag
from ..abc import IrAbc, SolidityAbc
from ..type_name.elementary_type_name import ElementaryTypeName
from .abc import ExpressionAbc


class ElementaryTypeNameExpression(ExpressionAbc):
    """
    TBD
    """

    _ast_node: SolcElementaryTypeNameExpression
    _parent: SolidityAbc  # TODO: make this more specific

    _type_name: ElementaryTypeName

    def __init__(
        self,
        init: IrInitTuple,
        elementary_type_name_expression: SolcElementaryTypeNameExpression,
        parent: SolidityAbc,
    ):
        super().__init__(init, elementary_type_name_expression, parent)
        self._type_name = ElementaryTypeName(
            init, elementary_type_name_expression.type_name, self
        )

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        yield from self._type_name

    @property
    def parent(self) -> SolidityAbc:
        return self._parent

    @property
    def type_name(self) -> ElementaryTypeName:
        return self._type_name

    @property
    def is_ref_to_state_variable(self) -> bool:
        return False

    @property
    def modifies_state(self) -> Set[Tuple[IrAbc, ModifiesStateFlag]]:
        return set()
