from __future__ import annotations

import re
import weakref
from bisect import bisect
from functools import lru_cache
from typing import TYPE_CHECKING, FrozenSet, Iterator, List, Optional, Tuple, Union

from wake.utils.decorators import weak_self_lru_cache

from ...regex_parser import SoliditySourceParser
from ..abc import is_not_none
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
    _parent: weakref.ReferenceType[Union[ContractDefinition, SourceUnit]]

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
        if self._documentation is not None:
            yield self._documentation

    def _parse_name_location(self) -> Tuple[int, int]:
        IDENTIFIER = r"[a-zA-Z$_][a-zA-Z0-9$_]*"
        STRUCT_RE = re.compile(
            r"^\s*struct\s+(?P<name>{identifier})".format(identifier=IDENTIFIER).encode(
                "utf-8"
            )
        )

        source = bytearray(self._source)
        _, stripped_sums = SoliditySourceParser.strip_comments(source)

        byte_start = self._ast_node.src.byte_offset
        match = STRUCT_RE.match(source)
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
            byte_start + match.start("name") + stripped,
            byte_start + match.end("name") + stripped,
        )

    @property
    def parent(self) -> Union[ContractDefinition, SourceUnit]:
        """
        Returns:
            Parent IR node.
        """
        return super().parent

    @property
    def children(self) -> Iterator[Union[VariableDeclaration, StructuredDocumentation]]:
        """
        Yields:
            Direct children of this node.
        """
        yield from self._members
        if self._documentation is not None:
            yield self._documentation

    @property
    def canonical_name(self) -> str:
        return self._canonical_name

    @property
    @weak_self_lru_cache(maxsize=2048)
    def declaration_string(self) -> str:
        ret = (
            f"struct {self.name}"
            + " {\n"
            + ";\n".join(f"    {member.declaration_string}" for member in self._members)
            + ";\n}"
        )
        if self._documentation is not None:
            return (
                "/// "
                + "\n///".join(line for line in self._documentation.text.splitlines())
                + "\n"
                + ret
            )
        else:
            return ret

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
