import logging
from bisect import bisect_right
from pathlib import Path
from typing import Iterator, List, Optional, Tuple

from wake.core import get_logger
from wake.ir.abc import IrAbc, SolidityAbc
from wake.ir.ast import (
    SolcContractDefinition,
    SolcEnumDefinition,
    SolcErrorDefinition,
    SolcEventDefinition,
    SolcFunctionDefinition,
    SolcImportDirective,
    SolcPragmaDirective,
    SolcSourceUnit,
    SolcStructDefinition,
    SolcUserDefinedValueTypeDefinition,
    SolcUsingForDirective,
    SolcVariableDeclaration,
)

from ...core.solidity_version import SolidityVersionRanges
from ..declarations.abc import DeclarationAbc
from ..declarations.contract_definition import ContractDefinition
from ..declarations.enum_definition import EnumDefinition
from ..declarations.error_definition import ErrorDefinition
from ..declarations.event_definition import EventDefinition
from ..declarations.function_definition import FunctionDefinition
from ..declarations.struct_definition import StructDefinition
from ..declarations.user_defined_value_type_definition import (
    UserDefinedValueTypeDefinition,
)
from ..declarations.variable_declaration import VariableDeclaration
from ..utils import IrInitTuple
from .import_directive import ImportDirective
from .pragma_directive import PragmaDirective
from .using_for_directive import UsingForDirective

logger = get_logger(__name__)


class SourceUnit(SolidityAbc):
    """
    Source unit is the root node.

    !!! warning
        Source unit [byte_location][wake.ir.abc.IrAbc.byte_location] does not cover the whole file.
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
    _events: List[EventDefinition]

    _version_ranges: SolidityVersionRanges
    _file: Path
    _cu_hash: bytes
    # TODO strip this from pickle?
    _lines_index: Optional[List[Tuple[bytes, int]]]  # lines with prefix length

    def __init__(
        self,
        init: IrInitTuple,
        source_unit: SolcSourceUnit,
    ):
        init.source_unit = self
        self._file = init.file
        self._cu_hash = init.cu.hash
        super().__init__(init, source_unit, None)
        self._file_source = init.source
        self._license = source_unit.license
        self._source_unit_name = source_unit.absolute_path
        self._version_ranges = init.cu.versions
        self._lines_index = None

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
        self._events = []
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
            elif isinstance(node, SolcEventDefinition):
                self._events.append(EventDefinition(init, node, self))
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
        for event in self._events:
            yield from event

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
        As opposed to [source][wake.ir.abc.IrAbc.source], this property returns the whole file source.

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
    def pragmas(self) -> Tuple[PragmaDirective, ...]:
        """
        Returns:
            Pragma directives present in the file.
        """
        return tuple(self._pragmas)

    @property
    def imports(self) -> Tuple[ImportDirective, ...]:
        """
        Returns:
            Import directives present in the file.
        """
        return tuple(self._imports)

    @property
    def declared_variables(self) -> Tuple[VariableDeclaration, ...]:
        """
        Should only return constants.

        Returns:
            Top-level variable declarations present in the file.
        """
        return tuple(self._declared_variables)

    @property
    def enums(self) -> Tuple[EnumDefinition, ...]:
        """
        Returns:
            Top-level enum definitions present in the file.
        """
        return tuple(self._enums)

    @property
    def functions(self) -> Tuple[FunctionDefinition, ...]:
        """
        Should only return [FunctionDefinitions][wake.ir.declarations.function_definition.FunctionDefinition] of the [FunctionKind.FREE_FUNCTION][wake.ir.enums.FunctionKind.FREE_FUNCTION] kind.

        Returns:
            Top-level function definitions present in the file.
        """
        return tuple(self._functions)

    @property
    def structs(self) -> Tuple[StructDefinition, ...]:
        """
        Returns:
            Top-level struct definitions present in the file.
        """
        return tuple(self._structs)

    @property
    def errors(self) -> Tuple[ErrorDefinition, ...]:
        """
        Returns:
            Top-level error definitions present in the file.
        """
        return tuple(self._errors)

    @property
    def user_defined_value_types(self) -> Tuple[UserDefinedValueTypeDefinition, ...]:
        """
        Returns:
            Top-level user-defined value type definitions present in the file.
        """
        return tuple(self._user_defined_value_types)

    @property
    def contracts(self) -> Tuple[ContractDefinition, ...]:
        """
        Returns:
            Contract definitions present in the file.
        """
        return tuple(self._contracts)

    @property
    def using_for_directives(self) -> Tuple[UsingForDirective, ...]:
        """
        Returns:
            Top-level using for directives present in the file.
        """
        return tuple(self._using_for_directives)

    @property
    def events(self) -> Tuple[EventDefinition, ...]:
        """
        Returns:
            Top-level event definitions present in the file.
        """
        return tuple(self._events)

    @property
    def version_ranges(self) -> SolidityVersionRanges:
        """
        !!! example
            ```python
            if "0.8.0" in node.version_ranges:
                print("The given file can be compiled with solc 0.8.0")
            ```

        Returns:
            Object listing all `solc` versions that can be used to compile the file containing this node.
        """
        return self._version_ranges

    @property
    def cu_hash(self) -> bytes:
        """
        Refer to [ReferenceResolver][wake.ir.reference_resolver.ReferenceResolver] for more information about compilation units.

        Returns:
            Hash of the compilation unit that produced this source unit.
        """
        return self._cu_hash

    @property
    def file(self) -> Path:
        """
        The absolute path to the source file that is represented by this node.

        Returns:
            Absolute path to the file containing this node.
        """
        return self._file

    def declarations_iter(self) -> Iterator[DeclarationAbc]:
        """
        Yields:
            All declarations present in the file (recursively).
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
        yield from self.events
        for contract in self.contracts:
            yield from contract.declarations_iter()

    def get_line_col_from_byte_offset(self, byte_offset: int) -> Tuple[int, int]:
        if self._lines_index is None:
            self._lines_index = []
            prefix_sum = 0

            for line in self._file_source.splitlines(keepends=True):
                self._lines_index.append((line, prefix_sum))
                prefix_sum += len(line)

        line_prefix_sums = [line[1] for line in self._lines_index]
        line = bisect_right(line_prefix_sums, byte_offset)
        # TODO different modes: UTF-16 code units, UTF-8 code units (bytes), UTF-8 code points (len of str)
        col = (
            len(
                self._lines_index[line - 1][0][
                    : byte_offset - self._lines_index[line - 1][1]
                ]
                .decode("utf-8")
                .encode("utf-16-le")
            )
            // 2
            + 1
        )
        # TODO line col zero-indexed or one-indexed?
        # currently returning one-indexed
        return line, col
