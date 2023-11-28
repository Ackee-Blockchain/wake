from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, FrozenSet, Iterator, Optional, Set, Tuple, Union

if TYPE_CHECKING:
    from ..expressions.identifier import Identifier
    from ..meta.identifier_path import IdentifierPathPart
    from ..expressions.member_access import MemberAccess
    from ..statements.inline_assembly import ExternalReference
    from ..expressions.unary_operation import UnaryOperation
    from ..expressions.binary_operation import BinaryOperation

from wake.ir.abc import SolidityAbc
from wake.ir.ast import (
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
from wake.ir.utils import IrInitTuple

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


class DeclarationAbc(SolidityAbc, ABC):
    """
    Abstract base class for all Solidity declarations.
    """

    _name: str
    _name_location: Optional[Tuple[int, int]]
    _references: Set[
        Union[
            Identifier,
            IdentifierPathPart,
            MemberAccess,
            ExternalReference,
            UnaryOperation,
            BinaryOperation,
        ]
    ]

    def __init__(
        self, init: IrInitTuple, solc_node: SolcDeclarationUnion, parent: SolidityAbc
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

    def register_reference(
        self,
        reference: Union[
            Identifier,
            IdentifierPathPart,
            MemberAccess,
            ExternalReference,
            UnaryOperation,
            BinaryOperation,
        ],
    ):
        self._references.add(reference)

    def unregister_reference(
        self,
        reference: Union[
            Identifier,
            IdentifierPathPart,
            MemberAccess,
            ExternalReference,
            UnaryOperation,
            BinaryOperation,
        ],
    ):
        self._references.remove(reference)

    def get_all_references(
        self, include_declarations: bool
    ) -> Iterator[
        Union[
            DeclarationAbc,
            Union[
                Identifier,
                IdentifierPathPart,
                MemberAccess,
                ExternalReference,
                UnaryOperation,
                BinaryOperation,
            ],
        ]
    ]:
        if include_declarations:
            yield self
        yield from self.references

    @abstractmethod
    def _parse_name_location(self) -> Tuple[int, int]:
        ...

    @property
    def name(self) -> str:
        """
        Returns:
            User-defined name of the declared object.
        """
        return self._name

    @property
    @abstractmethod
    def canonical_name(self) -> str:
        """
        !!! example
            `ContractName.StructName.FieldName` in the case of the `FieldName` [VariableDeclaration][wake.ir.declarations.variable_declaration.VariableDeclaration] declaration in the following example:
            ```solidity
            contract ContractName {
                struct StructName {
                    uint FieldName;
                }
            }
            ```

        Returns:
            Canonical name of the declared object.
        """
        ...

    @property
    @abstractmethod
    def declaration_string(self) -> str:
        """
        Declaration string that can be used for example in LSP hover. Does not include the declaration body, if any.
        Does not need to match the actual declaration string in the source code (may use a different order of keywords, for example).
        !!! example
            `:::solidity function foo(uint a, uint b) public payable virtual onlyOwner returns (uint)` of the [FunctionDefinition][wake.ir.declarations.function_definition.FunctionDefinition] declaration in the following example:
            ```solidity
            function foo(uint a, uint b) public onlyOwner virtual payable returns( uint ) {
                return a + b;
            }
            ```

        Returns:
            String representation of the declaration.
        """
        ...

    @property
    @abstractmethod
    def references(
        self,
    ) -> FrozenSet[
        Union[
            Identifier,
            IdentifierPathPart,
            MemberAccess,
            ExternalReference,
            UnaryOperation,
            BinaryOperation,
        ]
    ]:
        """
        Returns:
            Set of all IR nodes referencing this declaration.
        """
        ...

    @property
    def name_location(self) -> Tuple[int, int]:
        """
        Similar to [byte_location][wake.ir.abc.IrAbc.byte_location], but returns the location of the declaration name in the source code.

        Returns:
            Tuple of the start and end byte offsets of the declaration name in the source code.
        """
        if self._name_location is None:
            self._name_location = self._parse_name_location()
        return self._name_location
