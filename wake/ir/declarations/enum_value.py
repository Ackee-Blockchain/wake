from __future__ import annotations

import logging
import weakref
from typing import TYPE_CHECKING, FrozenSet, Iterator, Optional, Tuple

from ..abc import is_not_none
from ..meta.structured_documentation import StructuredDocumentation
from .abc import DeclarationAbc

if TYPE_CHECKING:
    from ..expressions.member_access import MemberAccess
    from .enum_definition import EnumDefinition

from wake.core import get_logger
from wake.ir.abc import IrAbc, SolidityAbc
from wake.ir.ast import SolcEnumValue
from wake.ir.utils import IrInitTuple

logger = get_logger(__name__)


class EnumValue(DeclarationAbc):
    """
    Definition of an enum value inside an enum definition.

    !!! example
        `GoLeft`, `GoRight`, `GoStraight`, `SitStill` in the following enum definition:
        ```solidity
        enum ActionChoices { GoLeft, GoRight, GoStraight, SitStill }
        ```
    """

    _ast_node: SolcEnumValue
    _parent: weakref.ReferenceType[EnumDefinition]

    _documentation: Optional[StructuredDocumentation]

    def __init__(self, init: IrInitTuple, value: SolcEnumValue, parent: SolidityAbc):
        super().__init__(init, value, parent)

        self._documentation = (
            StructuredDocumentation(init, value.documentation, self)
            if value.documentation is not None
            else None
        )

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        if self._documentation is not None:
            yield from self._documentation

    def _parse_name_location(self) -> Tuple[int, int]:
        src = self._ast_node.src
        return src.byte_offset, src.byte_offset + src.byte_length

    @property
    def parent(self) -> EnumDefinition:
        """
        Returns:
            Parent IR node.
        """
        return super().parent

    @property
    def children(self) -> Iterator[StructuredDocumentation]:
        """
        Yields:
            Direct children of this node.
        """
        if self._documentation is not None:
            yield self._documentation

    @property
    def canonical_name(self) -> str:
        return f"{self.parent.canonical_name}.{self._name}"

    @property
    def declaration_string(self) -> str:
        ret = f"{self.parent.name}.{self.name}"
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
    def documentation(self) -> Optional[StructuredDocumentation]:
        """
        Added in Solidity 0.8.30.

        Returns:
            [NatSpec](https://docs.soliditylang.org/en/latest/natspec-format.html) documentation string, if any.
        """
        return self._documentation

    @property
    def references(
        self,
    ) -> FrozenSet[MemberAccess]:
        """
        Returns:
            Set of all IR nodes referencing this enum value.
        """
        from ..expressions.member_access import MemberAccess

        refs = [is_not_none(r()) for r in self._references]

        try:
            ref = next(ref for ref in refs if not isinstance(ref, MemberAccess))
            raise AssertionError(f"Unexpected reference type: {ref}")
        except StopIteration:
            return frozenset(refs)  # pyright: ignore reportGeneralTypeIssues
