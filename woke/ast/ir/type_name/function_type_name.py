from woke.ast.enums import StateMutability, Visibility
from woke.ast.ir.abc import IrAbc
from woke.ast.ir.meta.parameter_list import ParameterList
from woke.ast.ir.type_name.abc import TypeNameAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcFunctionTypeName


class FunctionTypeName(TypeNameAbc):
    _ast_node: SolcFunctionTypeName
    _parent: IrAbc  # TODO: make this more specific

    __parameter_types: ParameterList
    __return_parameter_types: ParameterList
    __state_mutability: StateMutability
    __visibility: Visibility

    def __init__(
        self, init: IrInitTuple, function_type_name: SolcFunctionTypeName, parent: IrAbc
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

    @property
    def parent(self) -> IrAbc:
        return self._parent

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
