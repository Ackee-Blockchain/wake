from typing import Optional

from woke.ast.enums import StateMutability
from woke.ast.ir.abc import IrAbc, SolidityAbc
from woke.ast.ir.type_name.abc import TypeNameAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcElementaryTypeName


class ElementaryTypeName(TypeNameAbc):
    _ast_node: SolcElementaryTypeName
    _parent: SolidityAbc  # TODO: make this more specific

    __name: str
    __state_mutability: Optional[StateMutability]

    def __init__(
        self,
        init: IrInitTuple,
        elementary_type_name: SolcElementaryTypeName,
        parent: SolidityAbc,
    ):
        super().__init__(init, elementary_type_name, parent)
        self.__name = elementary_type_name.name
        self.__state_mutability = elementary_type_name.state_mutability

        from woke.ast.ir.expression.elementary_type_name_expression import (
            ElementaryTypeNameExpression,
        )

        # fix missing type descriptions in AST
        if self._type_descriptions.type_identifier is None and isinstance(
            parent, ElementaryTypeNameExpression
        ):
            self._type_descriptions = parent._type_descriptions

    @property
    def parent(self) -> SolidityAbc:
        return self._parent

    @property
    def name(self) -> str:
        return self.__name

    @property
    def state_mutability(self) -> Optional[StateMutability]:
        return self.__state_mutability
