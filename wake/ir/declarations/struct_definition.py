from __future__ import annotations

import re
from functools import lru_cache
from typing import TYPE_CHECKING, FrozenSet, Iterator, List, Optional, Tuple, Union

from ..meta.structured_documentation import StructuredDocumentation
from .abc import DeclarationAbc

if TYPE_CHECKING:
    from .contract_definition import ContractDefinition
    from ..expressions.identifier import Identifier
    from ..expressions.member_access import MemberAccess
    from ..meta.identifier_path import IdentifierPathPart
    from ..meta.source_unit import SourceUnit

from wake.ir.abc import IrAbc, SolidityAbc
from wake.ir.ast import SolcStructDefinition
from wake.ir.declarations.variable_declaration import VariableDeclaration
from wake.ir.enums import Visibility
from wake.ir.utils import IrInitTuple


class StructDefinition(DeclarationAbc):
    """
    Definition of a struct.

    !!! example
        ```solidity
        struct S {
            uint a;
            uint b;
        }
        ```
    """

    _ast_node: SolcStructDefinition
    _parent: Union[ContractDefinition, SourceUnit]

    _canonical_name: str
    _members: List[VariableDeclaration]
    _visibility: Visibility
    _documentation: Optional[StructuredDocumentation]

    def __init__(
        self,
        init: IrInitTuple,
        struct_definition: SolcStructDefinition,
        parent: SolidityAbc,
    ):
        super().__init__(init, struct_definition, parent)
        self._canonical_name = struct_definition.canonical_name
        # TODO scope
        self._visibility = struct_definition.visibility

        self._members = []
        for member in struct_definition.members:
            self._members.append(VariableDeclaration(init, member, self))
        self._documentation = (
            StructuredDocumentation(init, struct_definition.documentation, self)
            if struct_definition.documentation is not None
            else None
        )

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        for member in self._members:
            yield from member

    def _parse_name_location(self) -> Tuple[int, int]:
        IDENTIFIER = r"[a-zA-Z$_][a-zA-Z0-9$_]*"
        STRUCT_RE = re.compile(
            r"^\s*struct\s+(?P<name>{identifier})".format(identifier=IDENTIFIER).encode(
                "utf-8"
            )
        )

        byte_start = self._ast_node.src.byte_offset
        match = STRUCT_RE.match(self._source)
        assert match
        return byte_start + match.start("name"), byte_start + match.end("name")

    @property
    def parent(self) -> Union[ContractDefinition, SourceUnit]:
        """
        Returns:
            Parent IR node.
        """
        return self._parent

    @property
    def canonical_name(self) -> str:
        return self._canonical_name

    @property
    @lru_cache(maxsize=2048)
    def declaration_string(self) -> str:
        return (
            f"struct {self.name}"
            + " {\n"
            + ";\n".join(f"    {member.declaration_string}" for member in self._members)
            + ";\n}"
        )

    @property
    def members(self) -> Tuple[VariableDeclaration, ...]:
        """
        Returns:
            Tuple of member variable declarations.
        """
        return tuple(self._members)

    @property
    def documentation(self) -> Optional[StructuredDocumentation]:
        """
        Added in Solidity 0.8.20.

        Returns:
            [NatSpec](https://docs.soliditylang.org/en/latest/natspec-format.html) documentation string, if any.
        """
        return self._documentation

    @property
    def references(
        self,
    ) -> FrozenSet[Union[Identifier, IdentifierPathPart, MemberAccess,]]:
        """
        Returns:
            Set of all IR nodes referencing this struct.
        """
        from ..expressions.identifier import Identifier
        from ..expressions.member_access import MemberAccess
        from ..meta.identifier_path import IdentifierPathPart

        try:
            ref = next(
                ref
                for ref in self._references
                if not isinstance(ref, (Identifier, IdentifierPathPart, MemberAccess))
            )
            raise AssertionError(f"Unexpected reference type: {ref}")
        except StopIteration:
            return frozenset(
                self._references
            )  # pyright: ignore reportGeneralTypeIssues
