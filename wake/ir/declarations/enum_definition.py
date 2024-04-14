from __future__ import annotations

import logging
import re
from bisect import bisect
from functools import lru_cache
from typing import TYPE_CHECKING, FrozenSet, Iterator, List, Optional, Tuple, Union

from wake.core import get_logger
from wake.ir.ast import SolcEnumDefinition

from ...regex_parser import SoliditySourceParser
from ..abc import IrAbc, SolidityAbc
from ..meta.structured_documentation import StructuredDocumentation
from ..utils import IrInitTuple
from .abc import DeclarationAbc
from .enum_value import EnumValue

if TYPE_CHECKING:
    from ..expressions.identifier import Identifier
    from ..expressions.member_access import MemberAccess
    from ..meta.identifier_path import IdentifierPathPart
    from ..meta.source_unit import SourceUnit
    from .contract_definition import ContractDefinition


logger = get_logger(__name__)


class EnumDefinition(DeclarationAbc):
    """
    Definition of an enum.

    !!! example
        ```solidity
        enum ActionChoices { GoLeft, GoRight, GoStraight, SitStill }
        ```
    """

    _ast_node: SolcEnumDefinition
    _parent: Union[ContractDefinition, SourceUnit]

    _canonical_name: str
    _values: List[EnumValue]
    _documentation: Optional[StructuredDocumentation]

    def __init__(
        self, init: IrInitTuple, enum: SolcEnumDefinition, parent: SolidityAbc
    ):
        super().__init__(init, enum, parent)
        self._canonical_name = enum.canonical_name

        self._values = []
        for value in enum.members:
            self._values.append(EnumValue(init, value, self))
        self._documentation = (
            StructuredDocumentation(init, enum.documentation, self)
            if enum.documentation is not None
            else None
        )

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        for value in self._values:
            yield from value

    def _parse_name_location(self) -> Tuple[int, int]:
        IDENTIFIER = r"[a-zA-Z$_][a-zA-Z0-9$_]*"
        ENUM_RE = re.compile(
            r"^\s*enum\s+(?P<name>{identifier})".format(identifier=IDENTIFIER).encode(
                "utf-8"
            )
        )

        source = bytearray(self._source)
        _, stripped_sums = SoliditySourceParser.strip_comments(source)

        byte_start = self._ast_node.src.byte_offset
        match = ENUM_RE.match(source)
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
    def parent(self) -> Union[SourceUnit, ContractDefinition]:
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
            f"enum {self.name}"
            + " {\n"
            + ",\n".join(f"    {value.name}" for value in self._values)
            + "\n}"
        )

    @property
    def values(self) -> Tuple[EnumValue, ...]:
        """
        Returns:
            Enum values defined in this enum.
        """
        return tuple(self._values)

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
            Set of all IR nodes referencing this enum.
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
