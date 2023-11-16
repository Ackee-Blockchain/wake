from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Union

from wake.ir.types import (
    Address,
    Bool,
    Bytes,
    Fixed,
    FixedBytes,
    Int,
    String,
    Type,
    UFixed,
    UInt,
)

if TYPE_CHECKING:
    from ..declarations.user_defined_value_type_definition import (
        UserDefinedValueTypeDefinition,
    )
    from ..declarations.variable_declaration import VariableDeclaration
    from ..expressions.elementary_type_name_expression import (
        ElementaryTypeNameExpression,
    )
    from ..expressions.new_expression import NewExpression
    from ..meta.using_for_directive import UsingForDirective
    from .array_type_name import ArrayTypeName
    from .mapping import Mapping

from wake.ir.abc import SolidityAbc
from wake.ir.ast import SolcElementaryTypeName
from wake.ir.enums import StateMutability
from wake.ir.type_names.abc import TypeNameAbc
from wake.ir.utils import IrInitTuple


class ElementaryTypeName(TypeNameAbc):
    """
    Elementary type name.

    !!! example
        An elementary type name can be used:

        - inside a [VariableDeclaration][wake.ir.declarations.variable_declaration.VariableDeclaration]:
            - both occurrences of `:::solidity uint` on line 1,
            - `:::solidity int` on line 1,
            - `:::solidity string` on line 10,
            - the first occurrence of `:::solidity bytes` on line 15,
        - inside a [UserDefinedValueTypeDefinition][wake.ir.declarations.user_defined_value_type_definition.UserDefinedValueTypeDefinition]:
            - `:::solidity int` on line 7,
        - inside an [ElementaryTypeNameExpression][wake.ir.expressions.elementary_type_name_expression.ElementaryTypeNameExpression]:
            - `:::solidity int` on line 2,
        - inside a [NewExpression][wake.ir.expressions.new_expression.NewExpression]:
            - the second occurrence of `:::solidity bytes` on line 15,
        - inside a [UsingForDirective][wake.ir.meta.using_for_directive.UsingForDirective]:
            - `:::solidity uint` on line 5,
        - inside an [ArrayTypeName][wake.ir.type_names.array_type_name.ArrayTypeName]:
            - `:::solidity uint` on line 11,
        - inside a [Mapping][wake.ir.type_names.mapping.Mapping]:
            - `:::solidity address` on line 12.

        ```solidity linenums="1"
        function add(uint a, uint b) pure returns(int) {
            return int(a + b);
        }

        using {add} for uint;

        type MyInt is int;

        contract C {
            string public str;
            uint[10] arr;
            mapping(address => MyInt) map;

            function foo() public pure {
                bytes memory b = new bytes(10);
            }
        }
        ```
    """

    _ast_node: SolcElementaryTypeName
    _parent: Union[
        VariableDeclaration,
        UserDefinedValueTypeDefinition,
        ElementaryTypeNameExpression,
        NewExpression,
        UsingForDirective,
        ArrayTypeName,
        Mapping,
    ]

    _name: str
    _state_mutability: Optional[StateMutability]

    def __init__(
        self,
        init: IrInitTuple,
        elementary_type_name: SolcElementaryTypeName,
        parent: SolidityAbc,
    ):
        super().__init__(init, elementary_type_name, parent)
        self._name = elementary_type_name.name
        self._state_mutability = elementary_type_name.state_mutability

        from wake.ir.expressions.elementary_type_name_expression import (
            ElementaryTypeNameExpression,
        )

        # fix missing type descriptions in AST
        if self._type_descriptions.type_identifier is None and isinstance(
            parent, ElementaryTypeNameExpression
        ):
            self._type_descriptions = parent._type_descriptions

    @property
    def parent(
        self,
    ) -> Union[
        VariableDeclaration,
        UserDefinedValueTypeDefinition,
        ElementaryTypeNameExpression,
        NewExpression,
        UsingForDirective,
        ArrayTypeName,
        Mapping,
    ]:
        """
        When the parent is a [NewExpression][wake.ir.expressions.new_expression.NewExpression], this can only be `bytes` or `string`.

        Returns:
            Parent IR node.
        """
        return self._parent

    @property
    def type(
        self,
    ) -> Union[
        Address, Bool, Int, UInt, Fixed, UFixed, String, Bytes, FixedBytes, Type
    ]:
        """
        Returns either the generic [Type][wake.ir.types.Type] expression type (this is the case of a type conversion, for example `:::solidity address(0)`) or directly one of the elementary expression types.

        Returns:
            Type description.
        """
        t = super().type
        if not isinstance(
            t,
            (Address, Bool, Int, UInt, Fixed, UFixed, String, Bytes, FixedBytes, Type),
        ):
            raise TypeError(f"Unexpected type {t} {self.source}")
        assert isinstance(
            t,
            (Address, Bool, Int, UInt, Fixed, UFixed, String, Bytes, FixedBytes, Type),
        )
        return t

    @property
    def name(self) -> str:
        """
        !!! example
            For example `uint256`, `bool`, `string`, `bytes1` or `address`.

        !!! tip
            Instead of working with the name, it may be better to use the [type][wake.ir.type_names.elementary_type_name.ElementaryTypeName.type] property.

        Returns:
            Name of the elementary type.
        """
        return self._name

    @property
    def state_mutability(self) -> Optional[StateMutability]:
        """
        Is only set for `address` as either [StateMutability.PAYABLE][wake.ir.enums.StateMutability.PAYABLE] or [StateMutability.NONPAYABLE][wake.ir.enums.StateMutability.NONPAYABLE].

        Returns:
            State mutability of the `address` type.
        """
        return self._state_mutability
