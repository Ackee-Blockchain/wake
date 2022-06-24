from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING, List, Optional, Tuple, Union

if TYPE_CHECKING:
    from ..expression.identifier import Identifier
    from ..meta.identifier_path import IdentifierPath
    from ..expression.member_access import MemberAccess
    from ..type_name.user_defined_type_name import UserDefinedTypeName

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
        IdentifierPath,
        MemberAccess,
        UserDefinedTypeName,
    ]


class DeclarationAbc(IrAbc):
    _name: str
    _name_location: Optional[Tuple[int, int]]
    _references: List[ReferencingNodesUnion]

    def __init__(
        self, init: IrInitTuple, solc_node: SolcDeclarationUnion, parent: IrAbc
    ):
        super().__init__(init, solc_node, parent)
        self._name = solc_node.name
        if solc_node.name_location is None:
            self._name_location = None
        else:
            self._name_location = (
                solc_node.name_location.byte_offset,
                solc_node.name_location.byte_offset
                + solc_node.name_location.byte_length,
            )
        self._references = []

    def register_reference(self, reference: ReferencingNodesUnion):
        self._references.append(reference)

    @abstractmethod
    def _parse_name_location(self) -> Tuple[int, int]:
        ...

    @property
    def name(self) -> str:
        return self._name

    @property
    def name_location(self) -> Tuple[int, int]:
        if self._name_location is None:
            self._name_location = self._parse_name_location()
        return self._name_location

    @property
    def references(self) -> Tuple[ReferencingNodesUnion]:
        return tuple(self._references)
