from __future__ import annotations

from typing import Iterator, Union, TYPE_CHECKING

from ...expression_types import Function

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
        return self._parent

    @property
    def type(self) -> Function:
        t = super().type
        assert isinstance(t, Function)
        return t

    @property
    def parameter_types(self) -> ParameterList:
        return self.__parameter_types

    @property
    def return_parameter_types(self) -> ParameterList:
        return self.__return_parameter_types

    @property
    def state_mutability(self) -> StateMutability:
        return self.__state_mutability

    @property
    def visibility(self) -> Visibility:
        return self.__visibility
