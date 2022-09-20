import logging
from typing import Iterator, List, Optional, Tuple

from woke.ast.ir.abc import IrAbc, SolidityAbc
from woke.ast.nodes import (
    SolcContractDefinition,
    SolcEnumDefinition,
    SolcErrorDefinition,
    SolcFunctionDefinition,
    SolcImportDirective,
    SolcPragmaDirective,
    SolcSourceUnit,
    SolcStructDefinition,
    SolcUserDefinedValueTypeDefinition,
    SolcUsingForDirective,
    SolcVariableDeclaration,
)

from ..declaration.abc import DeclarationAbc
from ..declaration.contract_definition import ContractDefinition
from ..declaration.enum_definition import EnumDefinition
from ..declaration.error_definition import ErrorDefinition
from ..declaration.function_definition import FunctionDefinition
from ..declaration.struct_definition import StructDefinition
from ..declaration.user_defined_value_type_definition import (
    UserDefinedValueTypeDefinition,
)
from ..declaration.variable_declaration import VariableDeclaration
from ..utils import IrInitTuple
from .import_directive import ImportDirective
from .pragma_directive import PragmaDirective
from .using_for_directive import UsingForDirective

logger = logging.getLogger(__name__)


class SourceUnit(SolidityAbc):
    """
    Source unit is the root node.

    !!! warning
        Source unit [byte_location][woke.ast.ir.abc.IrAbc.byte_location] does not cover the whole file.
        Only lines 3-7 are covered by the source unit in the following example:
        ```solidity linenums="1"
        // SPDX-License-Identifier: MIT

        pragma solidity ^0.8;

        contract Foo {
            function bar() public {}
        }
        ```
        Also trailing newlines are not covered by the source unit.
    """

    _ast_node: SolcSourceUnit

    _file_source: bytes
    _license: Optional[str]
    _source_unit_name: str
    _pragmas: List[PragmaDirective]
    _imports: List[ImportDirective]
    _declared_variables: List[VariableDeclaration]
    _enums: List[EnumDefinition]
    _functions: List[FunctionDefinition]
    _structs: List[StructDefinition]
    _errors: List[ErrorDefinition]
    _user_defined_value_types: List[UserDefinedValueTypeDefinition]
    _contracts: List[ContractDefinition]
    _using_for_directives: List[UsingForDirective]

    def __init__(
        self,
        init: IrInitTuple,
        source_unit: SolcSourceUnit,
    ):
        super().__init__(init, source_unit, None)
        self._file_source = init.source
        self._license = source_unit.license
        self._source_unit_name = source_unit.absolute_path

        self._pragmas = []
        self._imports = []
        self._declared_variables = []
        self._enums = []
        self._functions = []
        self._structs = []
        self._errors = []
        self._user_defined_value_types = []
        self._contracts = []
        self._using_for_directives = []
        for node in source_unit.nodes:
            if isinstance(node, SolcPragmaDirective):
                self._pragmas.append(PragmaDirective(init, node, self))
            elif isinstance(node, SolcImportDirective):
                self._imports.append(ImportDirective(init, node, self))
            elif isinstance(node, SolcVariableDeclaration):
                self._declared_variables.append(VariableDeclaration(init, node, self))
            elif isinstance(node, SolcEnumDefinition):
                self._enums.append(EnumDefinition(init, node, self))
            elif isinstance(node, SolcFunctionDefinition):
                self._functions.append(FunctionDefinition(init, node, self))
            elif isinstance(node, SolcStructDefinition):
                self._structs.append(StructDefinition(init, node, self))
            elif isinstance(node, SolcErrorDefinition):
                self._errors.append(ErrorDefinition(init, node, self))
            elif isinstance(node, SolcUserDefinedValueTypeDefinition):
                self._user_defined_value_types.append(
                    UserDefinedValueTypeDefinition(init, node, self)
                )
            elif isinstance(node, SolcContractDefinition):
                self._contracts.append(ContractDefinition(init, node, self))
            elif isinstance(node, SolcUsingForDirective):
                self._using_for_directives.append(UsingForDirective(init, node, self))
            else:
                assert False, f"Unknown node type: {node}"

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        for pragma in self._pragmas:
            yield from pragma
        for import_directive in self._imports:
            yield from import_directive
        for variable_declaration in self._declared_variables:
            yield from variable_declaration
        for enum in self._enums:
            yield from enum
        for function in self._functions:
            yield from function
        for struct in self._structs:
            yield from struct
        for error in self._errors:
            yield from error
        for user_defined_value_type in self._user_defined_value_types:
            yield from user_defined_value_type
        for contract in self._contracts:
            yield from contract
        for using_for_directive in self._using_for_directives:
            yield from using_for_directive

    @property
    def parent(self) -> None:
        """
        Returns:
            Does not have a parent.
        """
        return None

    @property
    def file_source(self) -> bytes:
        """
        As opposed to [source][woke.ast.ir.abc.IrAbc.source], this property returns the whole file source.
        Returns:
            Source code of the file including trailing newlines and license string.
        """
        return self._file_source

    @property
    def license(self) -> Optional[str]:
        """
        !!! example
            Returns `MIT` for the following license comment:
            ```solidity
            // SPDX-License-Identifier: MIT
            ```
        Returns:
            License string of the file, if any.
        """
        return self._license

    @property
    def source_unit_name(self) -> str:
        """
        Returns:
            Source unit name of the file.
        """
        return self._source_unit_name

    @property
    def pragmas(self) -> Tuple[PragmaDirective]:
        """
        Returns:
            Pragma directives present in the file.
        """
        return tuple(self._pragmas)

    @property
    def imports(self) -> Tuple[ImportDirective]:
        """
        Returns:
            Import directives present in the file.
        """
        return tuple(self._imports)

    @property
    def declared_variables(self) -> Tuple[VariableDeclaration]:
        """
        Should only return constants.
        Returns:
            Top-level variable declarations present in the file.
        """
        return tuple(self._declared_variables)

    @property
    def enums(self) -> Tuple[EnumDefinition]:
        """
        Returns:
            Top-level enum definitions present in the file.
        """
        return tuple(self._enums)

    @property
    def functions(self) -> Tuple[FunctionDefinition]:
        """
        Should only return [FunctionDefinitions][woke.ast.ir.declaration.function_definition.FunctionDefinition] of the [FunctionKind.FREE_FUNCTION][woke.ast.enums.FunctionKind.FREE_FUNCTION] kind.
        Returns:
            Top-level function definitions present in the file.
        """
        return tuple(self._functions)

    @property
    def structs(self) -> Tuple[StructDefinition]:
        """
        Returns:
            Top-level struct definitions present in the file.
        """
        return tuple(self._structs)

    @property
    def errors(self) -> Tuple[ErrorDefinition]:
        """
        Returns:
            Top-level error definitions present in the file.
        """
        return tuple(self._errors)

    @property
    def user_defined_value_types(self) -> Tuple[UserDefinedValueTypeDefinition]:
        """
        Returns:
            Top-level user-defined value type definitions present in the file.
        """
        return tuple(self._user_defined_value_types)

    @property
    def contracts(self) -> Tuple[ContractDefinition]:
        """
        Returns:
            Contract definitions present in the file.
        """
        return tuple(self._contracts)

    @property
    def using_for_directives(self) -> Tuple[UsingForDirective]:
        """
        Returns:
            Top-level using for directives present in the file.
        """
        return tuple(self._using_for_directives)

    def declarations_iter(self) -> Iterator[DeclarationAbc]:
        """
        Yields:
            All declarations ([DeclarationAbc][woke.ast.ir.declaration.abc.DeclarationAbc]) present in the file (recursively).
        """
        yield from self.declared_variables
        yield from self.enums
        for enum in self.enums:
            yield from enum.values
        yield from self.functions
        yield from self.structs
        yield from self.errors
        yield from self.user_defined_value_types
        yield from self.contracts
        for contract in self.contracts:
            yield from contract.declarations_iter()
