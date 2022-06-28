from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Tuple

from .abc import DeclarationAbc

if TYPE_CHECKING:
    from .enum_definition import EnumDefinition

from woke.ast.ir.abc import IrAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcEnumValue

logger = logging.getLogger(__name__)


class EnumValue(DeclarationAbc):
    _ast_node: SolcEnumValue
    _parent: EnumDefinition

    def __init__(self, init: IrInitTuple, value: SolcEnumValue, parent: IrAbc):
        super().__init__(init, value, parent)

    def _parse_name_location(self) -> Tuple[int, int]:
        src = self._ast_node.src
        return src.byte_offset, src.byte_offset + src.byte_length

    @property
    def parent(self) -> EnumDefinition:
        return self._parent

    @property
    def canonical_name(self) -> str:
        return f"{self._parent.canonical_name}.{self._name}"
