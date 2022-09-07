from __future__ import annotations

from typing import Iterator, Union, TYPE_CHECKING

from ...types import Function

if TYPE_CHECKING:
    from ..declaration.variable_declaration import VariableDeclaration
    from ..meta.using_for_directive import UsingForDirective
    from .array_type_name import ArrayTypeName
    from .mapping import Mapping

from woke.ast.enums import StateMutability, Visibility
from woke.ast.ir.abc import IrAbc, SolidityAbc
from woke.ast.ir.meta.parameter_list import ParameterList
from woke.ast.ir.type_name.abc import TypeNameAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcFunctionTypeName


class FunctionTypeName(TypeNameAbc):
    """
    Function type name.

    !!! example
        A function type name (`:::solidity function (uint) returns(uint)`) can be used:

        - inside a [VariableDeclaration][woke.ast.ir.declaration.variable_declaration.VariableDeclaration] (lines 1 and 8),
        - inside a [UsingForDirective][woke.ast.ir.meta.using_for_directive.UsingForDirective] (line 5),
        - inside a [ArrayTypeName][woke.ast.ir.type_name.array_type_name.ArrayTypeName] (line 9),
        - inside a [Mapping][woke.ast.ir.type_name.mapping.Mapping] (line 11).

        ```solidity linenums="1"
        function test(function (uint) returns(uint) f) {
            f(10);
        }

        using {test} for function (uint) returns(uint);

        contract X {
            function (uint) returns(uint) x;
            function (uint) returns(uint)[] y;

            mapping(uint => function (uint) returns(uint)) map;

            function foo(uint a) public returns(uint){
                x = foo;
                y.push(foo);
            }
        }
        ```
    """
    _ast_node: SolcFunctionTypeName
    _parent: Union[VariableDeclaration, UsingForDirective, ArrayTypeName, Mapping]

    __parameter_types: ParameterList
    __return_parameter_types: ParameterList
    __state_mutability: StateMutability
    __visibility: Visibility

    def __init__(
        self,
        init: IrInitTuple,
        function_type_name: SolcFunctionTypeName,
        parent: SolidityAbc,
    ):
        super().__init__(init, function_type_name, parent)
        self.__parameter_types = ParameterList(
            init, function_type_name.parameter_types, self
        )
        self.__return_parameter_types = ParameterList(
            init, function_type_name.return_parameter_types, self
        )
        self.__state_mutability = function_type_name.state_mutability
        self.__visibility = function_type_name.visibility

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        yield from self.__parameter_types
        yield from self.__return_parameter_types

    @property
    def parent(self) -> Union[VariableDeclaration, UsingForDirective, ArrayTypeName, Mapping]:
        """
        Returns:
            Parent IR node.
        """
        return self._parent

    @property
    def type(self) -> Function:
        """
        Returns:
            Type description.
        """
        t = super().type
        assert isinstance(t, Function)
        return t

    @property
    def parameter_types(self) -> ParameterList:
        """
        Returns:
            Parameter list describing the function type name parameters.
        """
        return self.__parameter_types

    @property
    def return_parameter_types(self) -> ParameterList:
        """
        Returns:
            Parameter list describing the function type name return parameters.
        """
        return self.__return_parameter_types

    @property
    def state_mutability(self) -> StateMutability:
        """
        Returns:
            State mutability of the function type name.
        """
        return self.__state_mutability

    @property
    def visibility(self) -> Visibility:
        """
        Returns:
            Visibility of the function type name.
        """
        return self.__visibility
