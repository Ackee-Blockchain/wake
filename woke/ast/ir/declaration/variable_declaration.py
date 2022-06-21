from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional, Union

from woke.ast.enums import Mutability, StorageLocation, Visibility
from woke.ast.ir.abc import IrAbc

# from woke.ast.ir.meta.override_specifier import OverrideSpecifier
from woke.ast.ir.declaration.abc import DeclarationAbc
from woke.ast.ir.expression.abc import ExpressionAbc
from woke.ast.ir.meta.structured_documentation import StructuredDocumentation
from woke.ast.ir.type_name.abc import TypeNameAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcVariableDeclaration

# if TYPE_CHECKING:
# from .contract_definition import ContractDefinition
# from woke.ast.ir.meta.parameter_list import ParameterList
# from woke.ast.ir.meta.source_unit import SourceUnit
# from .struct_definition import StructDefinition
# from .variable_declaration_statement import VariableDeclarationStatement


logger = logging.getLogger(__name__)


class VariableDeclaration(DeclarationAbc):
    _ast_node: SolcVariableDeclaration
    # _parent: Union[ContractDefinition, ParameterList, SourceUnit, StructDefinition, VariableDeclarationStatement]

    __constant: bool
    __mutability: Optional[Mutability]
    __state_variable: bool
    __storage_location: StorageLocation
    __visibility: Visibility
    __documentation: Optional[StructuredDocumentation]
    __function_selector: Optional[bytes]
    __indexed: bool
    # __overrides: Optional[OverrideSpecifier] TODO
    __type_name: TypeNameAbc
    __value: Optional[ExpressionAbc]

    def __init__(
        self,
        init: IrInitTuple,
        variable_declaration: SolcVariableDeclaration,
        parent: IrAbc,
    ):
        super().__init__(init, variable_declaration, parent)
        self.__name = variable_declaration.name
        self.__constant = variable_declaration.constant
        self.__mutability = variable_declaration.mutability
        # TODO scope
        self.__state_variable = variable_declaration.state_variable
        self.__storage_location = variable_declaration.storage_location
        # TODO type descriptions?
        self.__visibility = variable_declaration.visibility
        # TODO base functions
        self.__documentation = (
            StructuredDocumentation(init, variable_declaration.documentation, self)
            if variable_declaration.documentation
            else None
        )
        self.__function_selector = (
            bytes.fromhex(variable_declaration.function_selector)
            if variable_declaration.function_selector
            else None
        )
        # TODO function selector?
        self.__indexed = variable_declaration.indexed or False
        # self.__overrides = OverrideSpecifier(init, variable_declaration.overrides, self) if variable_declaration.overrides else None

        # type name should not be None
        # prior 0.5.0, there was a `var` keyword which resulted in the type name being None
        assert (
            variable_declaration.type_name is not None
        ), "Variable declaration must have a type name"
        self.__type_name = TypeNameAbc.from_ast(
            init, variable_declaration.type_name, self
        )
        self.__value = (
            ExpressionAbc.from_ast(init, variable_declaration.value, self)
            if variable_declaration.value
            else None
        )

    # @property
    # def parent(self) -> Union[ContractDefinition, ParameterList, SourceUnit, StructDefinition, VariableDeclarationStatement]:
    # return self._parent

    @property
    def constant(self) -> bool:
        return self.__constant

    @property
    def mutability(self) -> Optional[Mutability]:
        return self.__mutability

    @property
    def is_state_variable(self) -> bool:
        return self.__state_variable

    @property
    def storage_location(self) -> StorageLocation:
        return self.__storage_location

    @property
    def visibility(self) -> Visibility:
        return self.__visibility

    @property
    def documentation(self) -> Optional[StructuredDocumentation]:
        return self.__documentation

    @property
    def function_selector(self) -> Optional[bytes]:
        return self.__function_selector

    @property
    def indexed(self) -> bool:
        return self.__indexed

    # @property
    # def overrides(self) -> Optional[OverrideSpecifier]:
    # return self.__overrides

    @property
    def type_name(self) -> TypeNameAbc:
        return self.__type_name

    @property
    def value(self) -> Optional[ExpressionAbc]:
        return self.__value
