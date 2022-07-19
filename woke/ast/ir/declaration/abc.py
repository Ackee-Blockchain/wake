from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING, FrozenSet, Iterator, Optional, Set, Tuple, Union

if TYPE_CHECKING:
    from ..expression.identifier import Identifier
    from ..meta.identifier_path import IdentifierPathPart
    from ..expression.member_access import MemberAccess
    from ..statement.inline_assembly import ExternalReference

from woke.ast.ir.abc import IrAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import (
    SolcContractDefinition,
    SolcEnumDefinition,
    SolcEnumValue,
    SolcErrorDefinition,
    SolcEventDefinition,
    SolcFunctionDefinition,
    SolcModifierDefinition,
    SolcStructDefinition,
    SolcUserDefinedValueTypeDefinition,
    SolcVariableDeclaration,
)

SolcDeclarationUnion = Union[
    SolcContractDefinition,
    SolcEnumDefinition,
    SolcEnumValue,
    SolcErrorDefinition,
    SolcEventDefinition,
    SolcFunctionDefinition,
    SolcModifierDefinition,
    SolcStructDefinition,
    SolcUserDefinedValueTypeDefinition,
    SolcVariableDeclaration,
]

if TYPE_CHECKING:
    ReferencingNodesUnion = Union[
        Identifier,
        IdentifierPathPart,
        MemberAccess,
        ExternalReference,
    ]


class DeclarationAbc(IrAbc):
    _name: str
    _name_location: Optional[Tuple[int, int]]
    _references: Set[ReferencingNodesUnion]

    def __init__(
        self, init: IrInitTuple, solc_node: SolcDeclarationUnion, parent: IrAbc
    ):
        super().__init__(init, solc_node, parent)
        self._name = solc_node.name
        if solc_node.name_location is None or solc_node.name_location.byte_offset < 0:
            self._name_location = None
        else:
            self._name_location = (
                solc_node.name_location.byte_offset,
                solc_node.name_location.byte_offset
                + solc_node.name_location.byte_length,
            )
        self._references = set()

    def register_reference(self, reference: ReferencingNodesUnion):
        self._references.add(reference)

    def unregister_reference(self, reference: ReferencingNodesUnion):
        self._references.remove(reference)

    def get_all_references(
        self, include_declarations: bool
    ) -> Iterator[Union[DeclarationAbc, ReferencingNodesUnion]]:
        if include_declarations:
            yield self
        yield from self.references

    @abstractmethod
    def _parse_name_location(self) -> Tuple[int, int]:
        ...

    @property
    def name(self) -> str:
        return self._name

    @property
    @abstractmethod
    def canonical_name(self) -> str:
        ...

    @property
    def name_location(self) -> Tuple[int, int]:
        if self._name_location is None:
            self._name_location = self._parse_name_location()
        return self._name_location

    @property
    def references(self) -> FrozenSet[ReferencingNodesUnion]:
        return frozenset(self._references)
