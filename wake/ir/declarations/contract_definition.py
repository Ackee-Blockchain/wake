from __future__ import annotations

import re
import weakref
from bisect import bisect
from functools import lru_cache, partial
from typing import TYPE_CHECKING, FrozenSet, Iterator, List, Optional, Set, Tuple, Union, Iterable

from wake.utils.decorators import weak_self_lru_cache

from ...regex_parser import SoliditySourceParser
from ..abc import IrAbc, is_not_none
from ..meta.inheritance_specifier import InheritanceSpecifier
from ..meta.using_for_directive import UsingForDirective
from ..reference_resolver import CallbackParams
from .abc import DeclarationAbc

if TYPE_CHECKING:
    from wake.compiler import SolcOutputContractInfo
    from ..expressions.identifier import Identifier
    from ..expressions.member_access import MemberAccess
    from ..meta.identifier_path import IdentifierPathPart
    from ..meta.source_unit import SourceUnit

from wake.ir.ast import (
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
from wake.ir.declarations.enum_definition import EnumDefinition
from wake.ir.declarations.error_definition import ErrorDefinition
from wake.ir.declarations.event_definition import EventDefinition
from wake.ir.declarations.function_definition import FunctionDefinition
from wake.ir.declarations.modifier_definition import ModifierDefinition
from wake.ir.declarations.struct_definition import StructDefinition
from wake.ir.declarations.user_defined_value_type_definition import (
    UserDefinedValueTypeDefinition,
)
from wake.ir.declarations.variable_declaration import VariableDeclaration
from wake.ir.enums import ContractKind
from wake.ir.meta.structured_documentation import StructuredDocumentation
from wake.ir.utils import IrInitTuple


class ContractDefinition(DeclarationAbc):
    """
    Definition of a contract, library or interface. [byte_location][wake.ir.abc.IrAbc.byte_location] also includes the contract body.

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
    _parent: weakref.ReferenceType[SourceUnit]

    _abstract: bool
    _base_contracts: List[InheritanceSpecifier]
    # ___dependencies
    _kind: ContractKind
    _fully_implemented: Optional[bool]
    _linearized_base_contracts: List[AstNodeId]
    # __scope
    _documentation: Optional[Union[StructuredDocumentation, str]]
    _compilation_info: Optional[SolcOutputContractInfo]
    _used_errors: List[AstNodeId]
    _enums: List[EnumDefinition]
    _errors: List[ErrorDefinition]
    _events: List[EventDefinition]
    _functions: List[FunctionDefinition]
    _modifiers: List[ModifierDefinition]
    _structs: List[StructDefinition]
    _user_defined_value_types: List[UserDefinedValueTypeDefinition]
    _using_for_directives: List[UsingForDirective]
    _declared_variables: List[VariableDeclaration]

    _used_event_ids: List[AstNodeId]
    _used_events: Set[weakref.ReferenceType[EventDefinition]]
    # _internal_function_ids

    _child_contracts: Set[weakref.ReferenceType[ContractDefinition]]

    def __init__(
        self, init: IrInitTuple, contract: SolcContractDefinition, parent: SourceUnit
    ):
        super().__init__(init, contract, parent)
        self._abstract = contract.abstract
        self._kind = contract.contract_kind
        self._fully_implemented = contract.fully_implemented
        self._linearized_base_contracts = list(contract.linearized_base_contracts)
        self._used_errors = (
            list(contract.used_errors) if contract.used_errors is not None else []
        )
        self._used_event_ids = (
            list(contract.used_events) if contract.used_events is not None else []
        )
        self._used_events = set()

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
        if init.contracts_info is not None and self.name in init.contracts_info:
            self._compilation_info = init.contracts_info[self.name]
        else:
            self._compilation_info = None

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
        init.reference_resolver.register_post_process_callback(
            self._post_process_events, priority=1
        )

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

    def __setstate__(self, state):
        super().__setstate__(state)
        self._used_events = set()
        self._child_contracts = set()

    @classmethod
    def _strip_weakrefs(cls, state: dict):
        super()._strip_weakrefs(state)
        del state["_used_events"]
        del state["_child_contracts"]

    def _post_process(self, callback_params: CallbackParams):
        base_contracts = []
        for base_contract in self._base_contracts:
            contract = base_contract.base_name.referenced_declaration
            assert isinstance(contract, ContractDefinition)
            contract._child_contracts.add(weakref.ref(self))
            base_contracts.append(contract)

        for error in self.used_errors:
            error._used_in.add(weakref.ref(self))

        # in case used_events are set in the AST in solc >= 0.8.20
        for event_id in self._used_event_ids:
            event = self._reference_resolver.resolve_node(
                event_id, self.source_unit.cu_hash
            )
            assert isinstance(event, EventDefinition)
            self._used_events.add(weakref.ref(event))

        # in case used_events are not set in the AST in solc < 0.8.20
        for event in self._events:
            self._used_events.add(weakref.ref(event))

        self._reference_resolver.register_destroy_callback(
            self.source_unit.file, partial(self._destroy, base_contracts, self.used_errors)
        )

    def _post_process_events(self, callback_params: CallbackParams):
        for base in self.linearized_base_contracts:
            for event in base.used_events:
                self._used_events.add(weakref.ref(event))

        # populate self._used_event_ids so it can be later used during pickle deserialization
        used_event_ids = []
        for event in self.used_events:
            event._used_in.add(weakref.ref(self))

            node_path_order = self._reference_resolver.get_node_path_order(
                event.ast_node_id, event.source_unit.cu_hash
            )
            used_event_ids.append(
                self._reference_resolver.get_ast_id_from_cu_node_path_order(
                    node_path_order, self.source_unit.cu_hash
                )
            )
        self._used_event_ids = used_event_ids

        self._reference_resolver.register_destroy_callback(
            self.source_unit.file, partial(self._destroy_events, self.used_events),
        )

    def _destroy(self, base_contracts: List[ContractDefinition], used_errors: Iterable[ErrorDefinition]) -> None:
        for base_contract in base_contracts:
            ref = next(c for c in base_contract._child_contracts if c() is self)
            base_contract._child_contracts.remove(ref)
        for error in used_errors:
            ref = next(c for c in error._used_in if c() is self)
            error._used_in.remove(ref)

    def _destroy_events(self, used_events: Iterable[EventDefinition]) -> None:
        for event in used_events:
            ref = next(c for c in event._used_in if c() is self)
            event._used_in.remove(ref)

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

        source = bytearray(self._source)
        _, stripped_sums = SoliditySourceParser.strip_comments(source)

        if self.kind == ContractKind.CONTRACT:
            match = CONTRACT_RE.match(source)
        elif self.kind == ContractKind.INTERFACE:
            match = INTERFACE_RE.match(source)
        elif self.kind == ContractKind.LIBRARY:
            match = LIBRARY_RE.match(source)
        else:
            raise ValueError(f"Unknown contract kind: {self.kind}")
        assert match

        if len(stripped_sums) == 0:
            stripped = 0
        else:
            index = bisect([s[0] for s in stripped_sums], match.start("name"))
            if index == 0:
                stripped = 0
            else:
                stripped = stripped_sums[index - 1][1]

        return (
            self.byte_location[0] + match.start("name") + stripped,
            self.byte_location[0] + match.end("name") + stripped,
        )

    @property
    def parent(self) -> SourceUnit:
        """
        Returns:
            Parent IR node.
        """
        return super().parent

    @property
    def children(
        self,
    ) -> Iterator[
        Union[
            InheritanceSpecifier,
            StructuredDocumentation,
            EnumDefinition,
            ErrorDefinition,
            EventDefinition,
            FunctionDefinition,
            ModifierDefinition,
            StructDefinition,
            UserDefinedValueTypeDefinition,
            UsingForDirective,
            VariableDeclaration,
        ]
    ]:
        """
        Yields:
            Direct children of this node.
        """
        yield from self._base_contracts
        if isinstance(self._documentation, StructuredDocumentation):
            yield self._documentation
        yield from self._enums
        yield from self._errors
        yield from self._events
        yield from self._functions
        yield from self._modifiers
        yield from self._structs
        yield from self._user_defined_value_types
        yield from self._using_for_directives
        yield from self._declared_variables

    @property
    def canonical_name(self) -> str:
        return self._name

    @property
    @weak_self_lru_cache(maxsize=2048)
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
        Is `False` if the [kind][wake.ir.declarations.contract_definition.ContractDefinition.kind] is [ContractKind.LIBRARY][wake.ir.enums.ContractKind.LIBRARY] or [ContractKind.INTERFACE][wake.ir.enums.ContractKind.INTERFACE].

        Returns:
            `True` if the contract is abstract, `False` otherwise.
        """
        return self._abstract

    @property
    def base_contracts(self) -> Tuple[InheritanceSpecifier, ...]:
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
        Does not return all child contracts (recursively).

        Returns:
            Contracts that list this contract in their [base_contracts][wake.ir.declarations.contract_definition.ContractDefinition.base_contracts] property.
        """
        return frozenset(is_not_none(c()) for c in self._child_contracts)

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
    def linearized_base_contracts(self) -> Tuple[ContractDefinition, ...]:
        """
        Returns:
            C3 linearized list of all base contracts.
        """
        base_contracts = []
        for base_contract in self._linearized_base_contracts:
            node = self._reference_resolver.resolve_node(
                base_contract, self.source_unit.cu_hash
            )
            assert isinstance(node, ContractDefinition)
            base_contracts.append(node)
        return tuple(base_contracts)

    @property
    def used_errors(self) -> FrozenSet[ErrorDefinition]:
        """
        Returns:
            Errors used in revert statements in this contract (or its base contracts) as well as all errors defined and inherited by the contract.
        """
        used_errors = set()
        for error in self._used_errors:
            node = self._reference_resolver.resolve_node(
                error, self.source_unit.cu_hash
            )
            assert isinstance(node, ErrorDefinition)
            used_errors.add(node)
        return frozenset(used_errors)

    @property
    def used_events(self) -> FrozenSet[EventDefinition]:
        """
        Returns:
            Events emitted by the contract (or its base contracts) as well as all events defined and inherited by the contract.
        """
        return frozenset(is_not_none(e()) for e in self._used_events)

    @property
    def documentation(self) -> Optional[Union[StructuredDocumentation, str]]:
        """
        Of [StructuredDocumentation][wake.ir.meta.structured_documentation.StructuredDocumentation] type since Solidity 0.6.3.

        Returns:
            [NatSpec](https://docs.soliditylang.org/en/latest/natspec-format.html) documentation of this contract, if any.
        """
        return self._documentation

    @property
    def compilation_info(self) -> Optional[SolcOutputContractInfo]:
        return self._compilation_info

    @property
    def enums(self) -> Tuple[EnumDefinition, ...]:
        """
        Returns:
            Enum definitions contained in this contract.
        """
        return tuple(self._enums)

    @property
    def errors(self) -> Tuple[ErrorDefinition, ...]:
        """
        Returns:
            Error definitions contained in this contract.
        """
        return tuple(self._errors)

    @property
    def events(self) -> Tuple[EventDefinition, ...]:
        """
        Returns:
            Event definitions contained in this contract.
        """
        return tuple(self._events)

    @property
    def functions(self) -> Tuple[FunctionDefinition, ...]:
        """
        Returns:
            Function definitions contained in this contract.
        """
        return tuple(self._functions)

    @property
    def modifiers(self) -> Tuple[ModifierDefinition, ...]:
        """
        Returns:
            Modifier definitions contained in this contract.
        """
        return tuple(self._modifiers)

    @property
    def structs(self) -> Tuple[StructDefinition, ...]:
        """
        Returns:
            Struct definitions contained in this contract.
        """
        return tuple(self._structs)

    @property
    def user_defined_value_types(self) -> Tuple[UserDefinedValueTypeDefinition, ...]:
        """
        Returns:
            User defined value type definitions contained in this contract.
        """
        return tuple(self._user_defined_value_types)

    @property
    def using_for_directives(self) -> Tuple[UsingForDirective, ...]:
        """
        Returns:
            Using for directives contained in this contract.
        """
        return tuple(self._using_for_directives)

    @property
    def declared_variables(self) -> Tuple[VariableDeclaration, ...]:
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

    @property
    def references(
        self,
    ) -> FrozenSet[Union[Identifier, IdentifierPathPart, MemberAccess,]]:
        """
        Returns:
            Set of all IR nodes referencing this contract.
        """
        from ..expressions.identifier import Identifier
        from ..expressions.member_access import MemberAccess
        from ..meta.identifier_path import IdentifierPathPart

        refs = [is_not_none(r()) for r in self._references]

        try:
            ref = next(
                ref
                for ref in refs
                if not isinstance(ref, (Identifier, IdentifierPathPart, MemberAccess))
            )
            raise AssertionError(f"Unexpected reference type: {ref}")
        except StopIteration:
            return frozenset(refs)  # pyright: ignore reportGeneralTypeIssues
