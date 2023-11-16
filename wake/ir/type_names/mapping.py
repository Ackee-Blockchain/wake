from __future__ import annotations

from typing import TYPE_CHECKING, Iterator, Optional, Tuple, Union

from .elementary_type_name import ElementaryTypeName
from .user_defined_type_name import UserDefinedTypeName

if TYPE_CHECKING:
    from ..declarations.variable_declaration import VariableDeclaration
    from ..meta.using_for_directive import UsingForDirective
    from .array_type_name import ArrayTypeName

import wake.ir.types as types
from wake.ir.abc import IrAbc, SolidityAbc
from wake.ir.ast import SolcMapping
from wake.ir.type_names.abc import TypeNameAbc
from wake.ir.utils import IrInitTuple


class Mapping(TypeNameAbc):
    """
    Mapping type name.

    !!! example
        A mapping type name can be used:

        - inside a [VariableDeclaration][wake.ir.declarations.variable_declaration.VariableDeclaration]:
            - `:::solidity mapping(address => uint)` on line 1,
            - `:::solidity mapping(address => mapping(address => uint))` on line 8,
        - inside a [UsingForDirective][wake.ir.meta.using_for_directive.UsingForDirective]:
            - `:::solidity mapping(address => uint)` on line 5,
        - inside an [ArrayTypeName][wake.ir.type_names.array_type_name.ArrayTypeName]:
            - `:::solidity mapping(address => uint)` on line 9,
        - inside a [Mapping][wake.ir.type_names.mapping.Mapping]:
            - `:::solidity mapping(address => uint)` on line 8.

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
    _key_name: Optional[str]
    _key_name_location: Optional[Tuple[int, int]]
    _value_name: Optional[str]
    _value_name_location: Optional[Tuple[int, int]]

    def __init__(self, init: IrInitTuple, mapping: SolcMapping, parent: SolidityAbc):
        super().__init__(init, mapping, parent)
        key_type = TypeNameAbc.from_ast(init, mapping.key_type, self)
        assert isinstance(key_type, (ElementaryTypeName, UserDefinedTypeName))
        self._key_type = key_type
        self._value_type = TypeNameAbc.from_ast(init, mapping.value_type, self)

        self._key_name = mapping.key_name
        if mapping.key_name_location is not None:
            self._key_name_location = (
                mapping.key_name_location.byte_offset,
                mapping.key_name_location.byte_offset
                + mapping.key_name_location.byte_length,
            )
        else:
            self._key_name_location = None

        self._value_name = mapping.value_name
        if mapping.value_name_location is not None:
            self._value_name_location = (
                mapping.value_name_location.byte_offset,
                mapping.value_name_location.byte_offset
                + mapping.value_name_location.byte_length,
            )
        else:
            self._value_name_location = None

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        yield from self._key_type
        yield from self._value_type

    @property
    def parent(
        self,
    ) -> Union[VariableDeclaration, UsingForDirective, ArrayTypeName, Mapping]:
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

        - an [ElementaryTypeName][wake.ir.type_names.elementary_type_name.ElementaryTypeName],
        - a [UserDefinedTypeName][wake.ir.type_names.user_defined_type_name.UserDefinedTypeName] of a [Contract][wake.ir.types.Contract] type,
        - a [UserDefinedTypeName][wake.ir.type_names.user_defined_type_name.UserDefinedTypeName] of an [Enum][wake.ir.types.Enum] type,
        - a [UserDefinedTypeName][wake.ir.type_names.user_defined_type_name.UserDefinedTypeName] of a [UserDefinedValueType][wake.ir.types.UserDefinedValueType] type.

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

    @property
    def key_name(self) -> Optional[str]:
        """
        !!! note
            Mapping key names were introduced in Solidity 0.8.18.

        !!! example
            Returns `account` in the following code:

            ```solidity
            mapping(address account => uint balance) public balances;
            ```

        Returns:
            Mapping key name, if present.
        """
        return self._key_name

    @property
    def key_name_location(self) -> Optional[Tuple[int, int]]:
        """
        !!! note
            Mapping key names were introduced in Solidity 0.8.18.

        Returns:
            Tuple of the start and end byte offsets of the [key_name][wake.ir.type_names.mapping.Mapping.key_name] in the source code, if present.
        """
        return self._key_name_location

    @property
    def value_name(self) -> Optional[str]:
        """
        !!! note
            Mapping value names were introduced in Solidity 0.8.18.

        !!! example
            Returns `balance` in the following code:

            ```solidity
            mapping(address account => uint balance) public balances;
            ```

        Returns:
            Mapping value name, if present.
        """
        return self._value_name

    @property
    def value_name_location(self) -> Optional[Tuple[int, int]]:
        """
        !!! note
            Mapping value names were introduced in Solidity 0.8.18.

        Returns:
            Tuple of the start and end byte offsets of the [value_name][wake.ir.type_names.mapping.Mapping.value_name] in the source code, if present.
        """
        return self._value_name_location
