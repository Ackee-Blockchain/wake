from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, List, Tuple, Union

from woke.ast.nodes import SolcEnumDefinition

from ..abc import IrAbc
from ..utils import IrInitTuple
from .abc import DeclarationAbc
from .enum_value import EnumValue

if TYPE_CHECKING:
    from ..meta.source_unit import SourceUnit
    from .contract_definition import ContractDefinition


logger = logging.getLogger(__name__)


class EnumDefinition(DeclarationAbc):
    _ast_node: SolcEnumDefinition
    _parent: Union[ContractDefinition, SourceUnit]

    __canonical_name: str
    __values: List[EnumValue]

    def __init__(self, init: IrInitTuple, enum: SolcEnumDefinition, parent: IrAbc):
        super().__init__(init, enum, parent)
        self.__canonical_name = enum.canonical_name

        self.__values = []
        for value in enum.members:
            self.__values.append(EnumValue(init, value, self))

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
        return self._parent

    @property
    def canonical_name(self) -> str:
        return self.__canonical_name

    @property
    def values(self) -> Tuple[EnumValue]:
        return tuple(self.__values)
