from __future__ import annotations

import logging
import re
from functools import lru_cache
from typing import TYPE_CHECKING, Iterator, List, Tuple, Union

from woke.ast.nodes import SolcEnumDefinition

from ..abc import IrAbc, SolidityAbc
from ..utils import IrInitTuple
from .abc import DeclarationAbc
from .enum_value import EnumValue

if TYPE_CHECKING:
    from ..meta.source_unit import SourceUnit
    from .contract_definition import ContractDefinition


logger = logging.getLogger(__name__)


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

    def __init__(
        self, init: IrInitTuple, enum: SolcEnumDefinition, parent: SolidityAbc
    ):
        super().__init__(init, enum, parent)
        self._canonical_name = enum.canonical_name

        self._values = []
        for value in enum.members:
            self._values.append(EnumValue(init, value, self))

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

        byte_start = self._ast_node.src.byte_offset
        match = ENUM_RE.match(self._source)
        assert match
        return byte_start + match.start("name"), byte_start + match.end("name")

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
    def values(self) -> Tuple[EnumValue]:
        """
        Returns:
            Enum values defined in this enum.
        """
        return tuple(self._values)
