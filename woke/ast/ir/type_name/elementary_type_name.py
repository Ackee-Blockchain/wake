from __future__ import annotations

from typing import Optional, Union, TYPE_CHECKING

from ...expression_types import Address, Bool, Int, UInt, String, Bytes, FixedBytes, Type, Fixed, UFixed

if TYPE_CHECKING:
    from ..declaration.user_defined_value_type_definition import UserDefinedValueTypeDefinition
    from ..declaration.variable_declaration import VariableDeclaration
    from ..expression.elementary_type_name_expression import ElementaryTypeNameExpression
    from ..expression.new_expression import NewExpression
    from ..meta.using_for_directive import UsingForDirective
    from .array_type_name import ArrayTypeName
    from .mapping import Mapping

from woke.ast.enums import StateMutability
from woke.ast.ir.abc import IrAbc, SolidityAbc
from woke.ast.ir.type_name.abc import TypeNameAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcElementaryTypeName


class ElementaryTypeName(TypeNameAbc):
    _ast_node: SolcElementaryTypeName
    _parent: Union[VariableDeclaration, UserDefinedValueTypeDefinition, ElementaryTypeNameExpression, NewExpression, UsingForDirective, ArrayTypeName, Mapping]

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
    def parent(self) -> Union[VariableDeclaration, UserDefinedValueTypeDefinition, ElementaryTypeNameExpression, NewExpression, UsingForDirective, ArrayTypeName, Mapping]:
        return self._parent

    @property
    def type(self) -> Union[Address, Bool, Int, UInt, Fixed, UFixed, String, Bytes, FixedBytes, Type]:
        t = super().type
        if not isinstance(t, (Address, Bool, Int, UInt, Fixed, UFixed, String, Bytes, FixedBytes, Type)):
            raise TypeError(f"Unexpected type {t} {self.source}")
        assert isinstance(t, (Address, Bool, Int, UInt, Fixed, UFixed, String, Bytes, FixedBytes, Type))
        return t

    @property
    def name(self) -> str:
        return self.__name

    @property
    def state_mutability(self) -> Optional[StateMutability]:
        return self.__state_mutability
