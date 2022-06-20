from __future__ import annotations

import logging
from typing import TYPE_CHECKING

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
        self.__name = value.name

    @property
    def parent(self) -> EnumDefinition:
        return self._parent
