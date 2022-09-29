from __future__ import annotations

import re
from functools import lru_cache, partial
from typing import TYPE_CHECKING, FrozenSet, Iterator, List, Optional, Set, Tuple, Union

from ..abc import IrAbc
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
    SolcStructuredDocumentation,
    SolcUserDefinedValueTypeDefinition,
    SolcUsingForDirective,
    SolcVariableDeclaration,
)


class ContractDefinition(DeclarationAbc):
    """
    Definition of a contract, library or interface. [byte_location][woke.ast.ir.abc.IrAbc.byte_location] also includes the contract body.

    !!! example
        ```solidity
        contract C {
            uint x;
            function f() public {}
        }
        ```

        ```solidity
        interface I {
            function f() external;
        }
        ```

        ```solidity
        library L {
            function f() internal pure returns (uint) {
                return 7;
            }
        }
        ```
    """

    _ast_node: SolcContractDefinition
    _parent: SourceUnit

    _abstract: bool
    _base_contracts: List[InheritanceSpecifier]
    # ___dependencies
    _kind: ContractKind
    _fully_implemented: Optional[bool]
    _linearized_base_contracts: List[AstNodeId]
    # __scope
    _documentation: Optional[Union[StructuredDocumentation, str]]
    # __used_errors
    _enums: List[EnumDefinition]
    _errors: List[ErrorDefinition]
    _events: List[EventDefinition]
    _functions: List[FunctionDefinition]
    _modifiers: List[ModifierDefinition]
    _structs: List[StructDefinition]
    _user_defined_value_types: List[UserDefinedValueTypeDefinition]
    _using_for_directives: List[UsingForDirective]
    _declared_variables: List[VariableDeclaration]

    _child_contracts: Set[ContractDefinition]

    def __init__(
        self, init: IrInitTuple, contract: SolcContractDefinition, parent: SourceUnit
    ):
        super().__init__(init, contract, parent)
        self._abstract = contract.abstract
        self._kind = contract.contract_kind
        self._fully_implemented = contract.fully_implemented
        self._linearized_base_contracts = list(contract.linearized_base_contracts)

        if contract.documentation is None:
            self._documentation = None
        elif isinstance(contract.documentation, SolcStructuredDocumentation):
            self._documentation = StructuredDocumentation(
                init, contract.documentation, self
            )
        elif isinstance(contract.documentation, str):
            self._documentation = contract.documentation
        else:
            raise TypeError(
                f"Unknown type of documentation: {type(contract.documentation)}"
            )

        self._base_contracts = []
        for base_contract in contract.base_contracts:
            self._base_contracts.append(InheritanceSpecifier(init, base_contract, self))
        self._child_contracts = set()

        self._enums = []
        self._errors = []
        self._events = []
        self._functions = []
        self._modifiers = []
        self._structs = []
        self._user_defined_value_types = []
        self._using_for_directives = []
        self._declared_variables = []

        for node in contract.nodes:
            if isinstance(node, SolcEnumDefinition):
                self._enums.append(EnumDefinition(init, node, self))
            elif isinstance(node, SolcErrorDefinition):
                self._errors.append(ErrorDefinition(init, node, self))
            elif isinstance(node, SolcEventDefinition):
                self._events.append(EventDefinition(init, node, self))
            elif isinstance(node, SolcFunctionDefinition):
                self._functions.append(FunctionDefinition(init, node, self))
            elif isinstance(node, SolcModifierDefinition):
                self._modifiers.append(ModifierDefinition(init, node, self))
            elif isinstance(node, SolcStructDefinition):
                self._structs.append(StructDefinition(init, node, self))
            elif isinstance(node, SolcUserDefinedValueTypeDefinition):
                self._user_defined_value_types.append(
                    UserDefinedValueTypeDefinition(init, node, self)
                )
            elif isinstance(node, SolcUsingForDirective):
                self._using_for_directives.append(UsingForDirective(init, node, self))
            elif isinstance(node, SolcVariableDeclaration):
                self._declared_variables.append(VariableDeclaration(init, node, self))

        init.reference_resolver.register_post_process_callback(self._post_process)

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        for base_contract in self._base_contracts:
            yield from base_contract
        if isinstance(self._documentation, StructuredDocumentation):
            yield from self._documentation
        for enum in self._enums:
            yield from enum
        for error in self._errors:
            yield from error
        for event in self._events:
            yield from event
        for function in self._functions:
            yield from function
        for modifier in self._modifiers:
            yield from modifier
        for struct in self._structs:
            yield from struct
        for user_defined_value_type in self._user_defined_value_types:
            yield from user_defined_value_type
        for using_for_directive in self._using_for_directives:
            yield from using_for_directive
        for declared_variable in self._declared_variables:
            yield from declared_variable

    def _post_process(self, callback_params: CallbackParams):
        base_contracts = []
        for base_contract in self._base_contracts:
            contract = base_contract.base_name.referenced_declaration
            assert isinstance(contract, ContractDefinition)
            contract._child_contracts.add(self)
            base_contracts.append(contract)

        self._reference_resolver.register_destroy_callback(
            self.file, partial(self._destroy, base_contracts)
        )

    def _destroy(self, base_contracts: List[ContractDefinition]) -> None:
        for base_contract in base_contracts:
            base_contract._child_contracts.remove(self)

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
        """
        Returns:
            Parent IR node.
        """
        return self._parent

    @property
    def canonical_name(self) -> str:
        return self._name

    @property
    @lru_cache(maxsize=2048)
    def declaration_string(self) -> str:
        ret = f"{'abstract ' if self.abstract else ''}{self.kind} {self.name}"
        ret += (
            " is " + ", ".join(spec.source for spec in self.base_contracts)
            if len(self.base_contracts) > 0
            else ""
        )
        if isinstance(self.documentation, StructuredDocumentation):
            return (
                "/// "
                + "\n///".join(line for line in self.documentation.text.splitlines())
                + "\n"
                + ret
            )
        elif isinstance(self.documentation, str):
            return (
                "/// "
                + "\n///".join(line for line in self.documentation.splitlines())
                + "\n"
                + ret
            )
        else:
            return ret

    @property
    def abstract(self) -> bool:
        """
        Is `False` if the [kind][woke.ast.ir.declaration.contract_definition.ContractDefinition.kind] is [ContractKind.LIBRARY][woke.ast.enums.ContractKind.LIBRARY] or [ContractKind.INTERFACE][woke.ast.enums.ContractKind.INTERFACE].

        Returns:
            `True` if the contract is abstract, `False` otherwise.
        """
        return self._abstract

    @property
    def base_contracts(self) -> Tuple[InheritanceSpecifier]:
        """
        Returns base contracts as specified in the source code. Does not return all base contracts (recursively).
        !!! example
            `A1` lists the interface `I` as a base contract.

            `A2` lists the interface `I` as a base contract.

            `B` lists the contracts `A1` and `A2` as base contracts.
            ```solidity
            interface I {}
            contract A1 is I {}
            contract A2 is I {}
            contract B is A1, A2 {}
            ```
        Returns:
            Base contracts of this contract.
        """
        return tuple(self._base_contracts)

    @property
    def child_contracts(self) -> FrozenSet[ContractDefinition]:
        """
        Returns:
            Contracts that list this contract in their [base_contracts][woke.ast.ir.declaration.contract_definition.ContractDefinition.base_contracts] property.
        """
        return frozenset(self._child_contracts)

    @property
    def kind(self) -> ContractKind:
        """
        Returns:
            Contract kind.
        """
        return self._kind

    @property
    def fully_implemented(self) -> Optional[bool]:
        """
        Is `None` when a file that imports this contract cannot be compiled. This may happen in the LSP server where partial project analysis is supported.
        Returns:
            `True` if all functions and modifiers of the contract are implemented, `False` otherwise.
        """
        return self._fully_implemented

    @property
    def linearized_base_contracts(self) -> Tuple[ContractDefinition]:
        """
        Returns:
            C3 linearized list of all base contracts.
        """
        base_contracts = []
        for base_contract in self._linearized_base_contracts:
            node = self._reference_resolver.resolve_node(base_contract, self._cu_hash)
            assert isinstance(node, ContractDefinition)
            base_contracts.append(node)
        return tuple(base_contracts)

    @property
    def documentation(self) -> Optional[Union[StructuredDocumentation, str]]:
        """
        Of [StructuredDocumentation][woke.ast.ir.meta.structured_documentation.StructuredDocumentation] type since Solidity 0.6.3.
        Returns:
            [NatSpec](https://docs.soliditylang.org/en/latest/natspec-format.html) documentation of this contract, if any.
        """
        return self._documentation

    @property
    def enums(self) -> Tuple[EnumDefinition]:
        """
        Returns:
            Enum definitions contained in this contract.
        """
        return tuple(self._enums)

    @property
    def errors(self) -> Tuple[ErrorDefinition]:
        """
        Returns:
            Error definitions contained in this contract.
        """
        return tuple(self._errors)

    @property
    def events(self) -> Tuple[EventDefinition]:
        """
        Returns:
            Event definitions contained in this contract.
        """
        return tuple(self._events)

    @property
    def functions(self) -> Tuple[FunctionDefinition]:
        """
        Returns:
            Function definitions contained in this contract.
        """
        return tuple(self._functions)

    @property
    def modifiers(self) -> Tuple[ModifierDefinition]:
        """
        Returns:
            Modifier definitions contained in this contract.
        """
        return tuple(self._modifiers)

    @property
    def structs(self) -> Tuple[StructDefinition]:
        """
        Returns:
            Struct definitions contained in this contract.
        """
        return tuple(self._structs)

    @property
    def user_defined_value_types(self) -> Tuple[UserDefinedValueTypeDefinition]:
        """
        Returns:
            User defined value type definitions contained in this contract.
        """
        return tuple(self._user_defined_value_types)

    @property
    def using_for_directives(self) -> Tuple[UsingForDirective]:
        """
        Returns:
            Using for directives contained in this contract.
        """
        return tuple(self._using_for_directives)

    @property
    def declared_variables(self) -> Tuple[VariableDeclaration]:
        """
        Returns:
            Variable declarations contained in this contract.
        """
        return tuple(self._declared_variables)

    def declarations_iter(self) -> Iterator[DeclarationAbc]:
        """
        Yields:
            All declarations contained in this contract.
        """
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
