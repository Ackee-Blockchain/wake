import logging
from typing import Iterator, List, Optional, Tuple

from woke.ast.ir.abc import IrAbc
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


class SourceUnit(IrAbc):
    _ast_node: SolcSourceUnit

    __license: Optional[str]
    __source_unit_name: str
    __pragmas: List[PragmaDirective]
    __imports: List[ImportDirective]
    __declared_variables: List[VariableDeclaration]
    __enums: List[EnumDefinition]
    __functions: List[FunctionDefinition]
    __structs: List[StructDefinition]
    __errors: List[ErrorDefinition]
    __user_defined_value_types: List[UserDefinedValueTypeDefinition]
    __contracts: List[ContractDefinition]
    __using_for_directives: List[UsingForDirective]

    def __init__(
        self,
        init: IrInitTuple,
        source_unit: SolcSourceUnit,
    ):
        super().__init__(init, source_unit, None)
        self.__license = source_unit.license
        self.__source_unit_name = source_unit.absolute_path

        self.__pragmas = []
        self.__imports = []
        self.__declared_variables = []
        self.__enums = []
        self.__functions = []
        self.__structs = []
        self.__errors = []
        self.__user_defined_value_types = []
        self.__contracts = []
        self.__using_for_directives = []
        for node in source_unit.nodes:
            if isinstance(node, SolcPragmaDirective):
                self.__pragmas.append(PragmaDirective(init, node, self))
            elif isinstance(node, SolcImportDirective):
                self.__imports.append(ImportDirective(init, node, self))
            elif isinstance(node, SolcVariableDeclaration):
                self.__declared_variables.append(VariableDeclaration(init, node, self))
            elif isinstance(node, SolcEnumDefinition):
                self.__enums.append(EnumDefinition(init, node, self))
            elif isinstance(node, SolcFunctionDefinition):
                self.__functions.append(FunctionDefinition(init, node, self))
            elif isinstance(node, SolcStructDefinition):
                self.__structs.append(StructDefinition(init, node, self))
            elif isinstance(node, SolcErrorDefinition):
                self.__errors.append(ErrorDefinition(init, node, self))
            elif isinstance(node, SolcUserDefinedValueTypeDefinition):
                self.__user_defined_value_types.append(
                    UserDefinedValueTypeDefinition(init, node, self)
                )
            elif isinstance(node, SolcContractDefinition):
                self.__contracts.append(ContractDefinition(init, node, self))
            elif isinstance(node, SolcUsingForDirective):
                self.__using_for_directives.append(UsingForDirective(init, node, self))
            else:
                assert False, f"Unknown node type: {node}"

    @property
    def parent(self) -> None:
        return None

    @property
    def license(self) -> Optional[str]:
        """
        The license string of the file (if present).
        """
        return self.__license

    @property
    def source_unit_name(self) -> str:
        """
        The source unit name of the file.
        """
        return self.__source_unit_name

    @property
    def pragmas(self) -> Tuple[PragmaDirective]:
        """
        A tuple of pragma directives present in the file.
        """
        return tuple(self.__pragmas)

    @property
    def imports(self) -> Tuple[ImportDirective]:
        """
        A tuple of import directives present in the file.
        """
        return tuple(self.__imports)

    @property
    def declared_variables(self) -> Tuple[VariableDeclaration]:
        """
        A tuple of top level variable declarations present in the file.
        """
        return tuple(self.__declared_variables)

    @property
    def enums(self) -> Tuple[EnumDefinition]:
        """
        A tuple of top level enum definitions present in the file.
        """
        return tuple(self.__enums)

    @property
    def functions(self) -> Tuple[FunctionDefinition]:
        """
        A tuple of top level function definitions present in the file.
        """
        return tuple(self.__functions)

    @property
    def structs(self) -> Tuple[StructDefinition]:
        """
        A tuple of top level struct definitions present in the file.
        """
        return tuple(self.__structs)

    @property
    def errors(self) -> Tuple[ErrorDefinition]:
        """
        A tuple of top level error definitions present in the file.
        """
        return tuple(self.__errors)

    @property
    def user_defined_value_types(self) -> Tuple[UserDefinedValueTypeDefinition]:
        """
        A tuple of top level user defined value type definitions present in the file.
        """
        return tuple(self.__user_defined_value_types)

    @property
    def contracts(self) -> Tuple[ContractDefinition]:
        """
        A tuple of top level contract definitions present in the file.
        """
        return tuple(self.__contracts)

    @property
    def using_for_directives(self) -> Tuple[UsingForDirective]:
        """
        A tuple of top level using for directives present in the file.
        """
        return tuple(self.__using_for_directives)

    @property
    def declarations(self) -> Iterator[DeclarationAbc]:
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
            yield from contract.declarations
