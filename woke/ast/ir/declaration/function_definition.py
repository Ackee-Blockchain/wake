from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional, Union

from ..statement.block import Block
from .abc import DeclarationAbc

if TYPE_CHECKING:
    from .contract_definition import ContractDefinition
    from ..meta.source_unit import SourceUnit

from woke.ast.enums import FunctionKind, StateMutability, Visibility
from woke.ast.ir.abc import IrAbc
from woke.ast.ir.meta.parameter_list import ParameterList
from woke.ast.ir.meta.structured_documentation import StructuredDocumentation
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcFunctionDefinition


class FunctionDefinition(DeclarationAbc):
    _ast_node: SolcFunctionDefinition
    _parent: Union[ContractDefinition, SourceUnit]

    __implemented: bool
    __kind: FunctionKind
    # __modifiers: List[ModifierInvocation]
    __parameters: ParameterList
    __return_parameters: ParameterList
    # __scope
    __state_mutability: StateMutability
    __virtual: bool
    __visibility: Visibility
    # __base_functions
    __documentation: Optional[StructuredDocumentation]
    # __function_selector
    __body: Optional[Block]
    # __overrides: Optional[OverrideSpecifier]

    def __init__(
        self, init: IrInitTuple, function: SolcFunctionDefinition, parent: IrAbc
    ):
        super().__init__(init, function, parent)
        self.__name = function.name
        self.__implemented = function.implemented
        self.__kind = function.kind
        # self.__modifiers = function.modifiers
        self.__parameters = ParameterList(init, function.parameters, self)
        self.__return_parameters = ParameterList(init, function.return_parameters, self)
        # self.__scope = function.scope
        self.__state_mutability = function.state_mutability
        self.__virtual = function.virtual
        self.__visibility = function.visibility
        # self.__base_functions = function.base_functions
        self.__documentation = (
            StructuredDocumentation(init, function.documentation, self)
            if function.documentation
            else None
        )
        # self.__function_selector = function.function_selector
        self.__body = Block(init, function.body, self) if function.body else None
        # self.__overrides = OverrideSpecifier(init, function.overrides, self) if function.overrides else None

    @property
    def parent(self) -> Union[ContractDefinition, SourceUnit]:
        return self._parent

    @property
    def implemented(self) -> bool:
        return self.__implemented

    @property
    def kind(self) -> FunctionKind:
        return self.__kind

    @property
    def parameters(self) -> ParameterList:
        return self.__parameters

    @property
    def return_parameters(self) -> ParameterList:
        return self.__return_parameters

    @property
    def state_mutability(self) -> StateMutability:
        return self.__state_mutability

    @property
    def virtual(self) -> bool:
        return self.__virtual

    @property
    def visibility(self) -> Visibility:
        return self.__visibility

    @property
    def documentation(self) -> Optional[StructuredDocumentation]:
        return self.__documentation

    @property
    def body(self) -> Optional[Block]:
        return self.__body
