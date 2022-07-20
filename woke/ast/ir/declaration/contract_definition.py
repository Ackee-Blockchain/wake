from __future__ import annotations

import re
from functools import partial
from typing import TYPE_CHECKING, FrozenSet, Iterator, List, Optional, Set, Tuple

from ..meta.inheritance_specifier import InheritanceSpecifier
from ..meta.using_for_directive import UsingForDirective
from ..reference_resolver import CallbackParams
from .abc import DeclarationAbc

if TYPE_CHECKING:
    from ..meta.source_unit import SourceUnit

from woke.ast.enums import ContractKind
from woke.ast.ir.declaration.enum_definition import EnumDefinition
from woke.ast.ir.declaration.error_definition import ErrorDefinition
from woke.ast.ir.declaration.event_definition import EventDefinition
from woke.ast.ir.declaration.function_definition import FunctionDefinition
from woke.ast.ir.declaration.modifier_definition import ModifierDefinition
from woke.ast.ir.declaration.struct_definition import StructDefinition
from woke.ast.ir.declaration.user_defined_value_type_definition import (
    UserDefinedValueTypeDefinition,
)
from woke.ast.ir.declaration.variable_declaration import VariableDeclaration
from woke.ast.ir.meta.structured_documentation import StructuredDocumentation
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import (
    AstNodeId,
    SolcContractDefinition,
    SolcEnumDefinition,
    SolcErrorDefinition,
    SolcEventDefinition,
    SolcFunctionDefinition,
    SolcModifierDefinition,
    SolcStructDefinition,
    SolcUserDefinedValueTypeDefinition,
    SolcUsingForDirective,
    SolcVariableDeclaration,
)


class ContractDefinition(DeclarationAbc):
    _ast_node: SolcContractDefinition
    _parent: SourceUnit

    __abstract: bool
    __base_contracts: List[InheritanceSpecifier]
    # ___dependencies
    __kind: ContractKind
    __fully_implemented: Optional[bool]
    __linearized_base_contracts: List[AstNodeId]
    # __scope
    __documentation: Optional[StructuredDocumentation]
    # __user_errors
    __enums: List[EnumDefinition]
    __errors: List[ErrorDefinition]
    __events: List[EventDefinition]
    __functions: List[FunctionDefinition]
    __modifiers: List[ModifierDefinition]
    __structs: List[StructDefinition]
    __user_defined_value_types: List[UserDefinedValueTypeDefinition]
    __using_for_directives: List[UsingForDirective]
    __declared_variables: List[VariableDeclaration]

    __child_contracts: Set[ContractDefinition]

    def __init__(
        self, init: IrInitTuple, contract: SolcContractDefinition, parent: SourceUnit
    ):
        super().__init__(init, contract, parent)
        self.__abstract = contract.abstract
        self.__kind = contract.contract_kind
        self.__fully_implemented = contract.fully_implemented
        self.__linearized_base_contracts = list(contract.linearized_base_contracts)
        self.__documentation = (
            StructuredDocumentation(init, contract.documentation, self)
            if contract.documentation
            else None
        )

        self.__base_contracts = []
        for base_contract in contract.base_contracts:
            self.__base_contracts.append(
                InheritanceSpecifier(init, base_contract, self)
            )
        self.__child_contracts = set()

        self.__enums = []
        self.__errors = []
        self.__events = []
        self.__functions = []
        self.__modifiers = []
        self.__structs = []
        self.__user_defined_value_types = []
        self.__using_for_directives = []
        self.__declared_variables = []

        for node in contract.nodes:
            if isinstance(node, SolcEnumDefinition):
                self.__enums.append(EnumDefinition(init, node, self))
            elif isinstance(node, SolcErrorDefinition):
                self.__errors.append(ErrorDefinition(init, node, self))
            elif isinstance(node, SolcEventDefinition):
                self.__events.append(EventDefinition(init, node, self))
            elif isinstance(node, SolcFunctionDefinition):
                self.__functions.append(FunctionDefinition(init, node, self))
            elif isinstance(node, SolcModifierDefinition):
                self.__modifiers.append(ModifierDefinition(init, node, self))
            elif isinstance(node, SolcStructDefinition):
                self.__structs.append(StructDefinition(init, node, self))
            elif isinstance(node, SolcUserDefinedValueTypeDefinition):
                self.__user_defined_value_types.append(
                    UserDefinedValueTypeDefinition(init, node, self)
                )
            elif isinstance(node, SolcUsingForDirective):
                self.__using_for_directives.append(UsingForDirective(init, node, self))
            elif isinstance(node, SolcVariableDeclaration):
                self.__declared_variables.append(VariableDeclaration(init, node, self))

        init.reference_resolver.register_post_process_callback(self.__post_process)

    def __post_process(self, callback_params: CallbackParams):
        base_contracts = []
        for base_contract in self.__base_contracts:
            contract = base_contract.base_name.referenced_declaration
            assert isinstance(contract, ContractDefinition)
            contract.__child_contracts.add(self)
            base_contracts.append(contract)

        self._reference_resolver.register_destroy_callback(
            self.file, partial(self.__destroy, base_contracts)
        )

    def __destroy(self, base_contracts: List[ContractDefinition]) -> None:
        for base_contract in base_contracts:
            base_contract.__child_contracts.remove(self)

    def _parse_name_location(self) -> Tuple[int, int]:
        IDENTIFIER = r"[a-zA-Z$_][a-zA-Z0-9$_]*"
        CONTRACT_RE = re.compile(
            r"^\s*(abstract\s)?\s*contract\s+(?P<name>{identifier})".format(
                identifier=IDENTIFIER
            ).encode("utf-8")
        )
        INTERFACE_RE = re.compile(
            r"^\s*interface\s+(?P<name>{identifier})".format(
                identifier=IDENTIFIER
            ).encode("utf-8")
        )
        LIBRARY_RE = re.compile(
            r"^\s*library\s+(?P<name>{identifier})".format(
                identifier=IDENTIFIER
            ).encode("utf-8")
        )

        if self.kind == ContractKind.CONTRACT:
            match = CONTRACT_RE.match(self._source)
        elif self.kind == ContractKind.INTERFACE:
            match = INTERFACE_RE.match(self._source)
        elif self.kind == ContractKind.LIBRARY:
            match = LIBRARY_RE.match(self._source)
        else:
            raise ValueError(f"Unknown contract kind: {self.kind}")
        assert match

        return self.byte_location[0] + match.start("name"), self.byte_location[
            0
        ] + match.end("name")

    @property
    def parent(self) -> SourceUnit:
        return self._parent

    @property
    def canonical_name(self) -> str:
        return self._name

    @property
    def abstract(self) -> bool:
        return self.__abstract

    @property
    def base_contracts(self) -> Tuple[InheritanceSpecifier]:
        return tuple(self.__base_contracts)

    @property
    def child_contracts(self) -> FrozenSet[ContractDefinition]:
        return frozenset(self.__child_contracts)

    @property
    def kind(self) -> ContractKind:
        return self.__kind

    @property
    def fully_implemented(self) -> Optional[bool]:
        return self.__fully_implemented

    @property
    def linearized_base_contracts(self) -> Tuple[ContractDefinition]:
        base_contracts = []
        for base_contract in self.__linearized_base_contracts:
            node = self._reference_resolver.resolve_node(base_contract, self._cu_hash)
            assert isinstance(node, ContractDefinition)
            base_contracts.append(node)
        return tuple(base_contracts)

    @property
    def documentation(self) -> Optional[StructuredDocumentation]:
        return self.__documentation

    @property
    def enums(self) -> Tuple[EnumDefinition]:
        return tuple(self.__enums)

    @property
    def errors(self) -> Tuple[ErrorDefinition]:
        return tuple(self.__errors)

    @property
    def events(self) -> Tuple[EventDefinition]:
        return tuple(self.__events)

    @property
    def functions(self) -> Tuple[FunctionDefinition]:
        return tuple(self.__functions)

    @property
    def modifiers(self) -> Tuple[ModifierDefinition]:
        return tuple(self.__modifiers)

    @property
    def structs(self) -> Tuple[StructDefinition]:
        return tuple(self.__structs)

    @property
    def user_defined_value_types(self) -> Tuple[UserDefinedValueTypeDefinition]:
        return tuple(self.__user_defined_value_types)

    @property
    def using_for_directives(self) -> Tuple[UsingForDirective]:
        return tuple(self.__using_for_directives)

    @property
    def declared_variables(self) -> Tuple[VariableDeclaration]:
        return tuple(self.__declared_variables)

    @property
    def declarations(self) -> Iterator[DeclarationAbc]:
        yield from self.enums
        for enum in self.enums:
            yield from enum.values
        yield from self.errors
        yield from self.events
        yield from self.functions
        yield from self.modifiers
        yield from self.structs
        yield from self.user_defined_value_types
        yield from self.declared_variables
