from __future__ import annotations

import re
from bisect import bisect
from functools import lru_cache
from typing import TYPE_CHECKING, FrozenSet, Iterator, Tuple, Union

from ...regex_parser import SoliditySourceParser
from ..type_names.elementary_type_name import ElementaryTypeName
from .abc import DeclarationAbc

if TYPE_CHECKING:
    from .contract_definition import ContractDefinition
    from ..expressions.identifier import Identifier
    from ..expressions.member_access import MemberAccess
    from ..meta.identifier_path import IdentifierPathPart
    from ..meta.source_unit import SourceUnit

from wake.ir.abc import IrAbc, SolidityAbc
from wake.ir.ast import SolcUserDefinedValueTypeDefinition
from wake.ir.utils import IrInitTuple


class UserDefinedValueTypeDefinition(DeclarationAbc):
    """
    Definition of a user defined value type.

    !!! example
        ```solidity
        type MyInt is uint;
        ```
    """

    _ast_node: SolcUserDefinedValueTypeDefinition
    _parent: Union[ContractDefinition, SourceUnit]

    _underlying_type: ElementaryTypeName

    def __init__(
        self,
        init: IrInitTuple,
        user_defined_value_type_definition: SolcUserDefinedValueTypeDefinition,
        parent: SolidityAbc,
    ):
        super().__init__(init, user_defined_value_type_definition, parent)
        self._underlying_type = ElementaryTypeName(
            init, user_defined_value_type_definition.underlying_type, self
        )

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        yield from self._underlying_type

    def _parse_name_location(self) -> Tuple[int, int]:
        IDENTIFIER = r"[a-zA-Z$_][a-zA-Z0-9$_]*"
        USER_DEF_VAL_TYPE_RE = re.compile(
            r"^\s*type\s+(?P<name>{identifier})".format(identifier=IDENTIFIER).encode(
                "utf-8"
            )
        )

        source = bytearray(self._source)
        _, stripped_sums = SoliditySourceParser.strip_comments(source)

        byte_start = self._ast_node.src.byte_offset
        match = USER_DEF_VAL_TYPE_RE.match(source)
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
        return self._parent

    @property
    @lru_cache(maxsize=2048)
    def canonical_name(self) -> str:
        from .contract_definition import ContractDefinition

        if isinstance(self._parent, ContractDefinition):
            return f"{self._parent.canonical_name}.{self._name}"
        return self._name

    @property
    @lru_cache(maxsize=2048)
    def declaration_string(self) -> str:
        return f"type {self.name} is {self._underlying_type.source}"

    @property
    def underlying_type(self) -> ElementaryTypeName:
        """
        Returns:
            Underlying type of the user defined value type.
        """
        return self._underlying_type

    @property
    def references(
        self,
    ) -> FrozenSet[Union[Identifier, IdentifierPathPart, MemberAccess,]]:
        """
        Returns:
            Set of all IR nodes referencing this user defined value type.
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
