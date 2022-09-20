from __future__ import annotations

from typing import Iterator, Union, TYPE_CHECKING

from .elementary_type_name import ElementaryTypeName
from .user_defined_type_name import UserDefinedTypeName

if TYPE_CHECKING:
    from ..declaration.variable_declaration import VariableDeclaration
    from ..meta.using_for_directive import UsingForDirective
    from .array_type_name import ArrayTypeName

import woke.ast.types as types
from woke.ast.ir.abc import IrAbc, SolidityAbc
from woke.ast.ir.type_name.abc import TypeNameAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcMapping


class Mapping(TypeNameAbc):
    """
    Mapping type name.

    !!! example
        A mapping type name can be used:

        - inside a [VariableDeclaration][woke.ast.ir.declaration.variable_declaration.VariableDeclaration]:
            - `:::solidity mapping(address => uint)` in line 1,
            - `:::solidity mapping(address => mapping(address => uint))` in line 8,
        - inside a [UsingForDirective][woke.ast.ir.meta.using_for_directive.UsingForDirective]:
            - `:::solidity mapping(address => uint)` in line 5,
        - inside an [ArrayTypeName][woke.ast.ir.type_name.array_type_name.ArrayTypeName]:
            - `:::solidity mapping(address => uint)` in line 9,
        - inside a [Mapping][woke.ast.ir.type_name.mapping.Mapping]:
            - `:::solidity mapping(address => uint)` in line 8.

        ```solidity linenums="1"
        function remove(mapping(address => uint) storage balances, address account) {
            delete balances[account];
        }

        using {remove} for mapping(address => uint);

        contract C {
            mapping(address => mapping(address => uint)) public allowances;
            mapping(address => uint)[2] public balances;
        }
        ```
    """
    _ast_node: SolcMapping
    _parent: Union[VariableDeclaration, UsingForDirective, ArrayTypeName, Mapping]

    _key_type: Union[ElementaryTypeName, UserDefinedTypeName]
    _value_type: TypeNameAbc

    def __init__(self, init: IrInitTuple, mapping: SolcMapping, parent: SolidityAbc):
        super().__init__(init, mapping, parent)
        key_type = TypeNameAbc.from_ast(init, mapping.key_type, self)
        assert isinstance(key_type, (ElementaryTypeName, UserDefinedTypeName))
        self._key_type = key_type
        self._value_type = TypeNameAbc.from_ast(init, mapping.value_type, self)

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        yield from self._key_type
        yield from self._value_type

    @property
    def parent(self) -> Union[VariableDeclaration, UsingForDirective, ArrayTypeName, Mapping]:
        """
        Returns:
            Parent IR node.
        """
        return self._parent

    @property
    def type(self) -> types.Mapping:
        """
        Returns:
            Type description.
        """
        t = super().type
        assert isinstance(t, types.Mapping)
        return t

    @property
    def key_type(self) -> Union[ElementaryTypeName, UserDefinedTypeName]:
        """
        Can only be:

        - an [ElementaryTypeName][woke.ast.ir.type_name.elementary_type_name.ElementaryTypeName],
        - a [UserDefinedTypeName][woke.ast.ir.type_name.user_defined_type_name.UserDefinedTypeName] of a [Contract][woke.ast.types.Contract] type,
        - a [UserDefinedTypeName][woke.ast.ir.type_name.user_defined_type_name.UserDefinedTypeName] of an [Enum][woke.ast.types.Enum] type,
        - a [UserDefinedTypeName][woke.ast.ir.type_name.user_defined_type_name.UserDefinedTypeName] of a [UserDefinedValueType][woke.ast.types.UserDefinedValueType] type.
        Returns:
            Mapping key type name.
        """
        return self._key_type

    @property
    def value_type(self) -> TypeNameAbc:
        """
        Returns:
            Mapping value type name.
        """
        return self._value_type
