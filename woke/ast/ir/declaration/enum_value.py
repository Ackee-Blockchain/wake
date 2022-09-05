from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Tuple

from .abc import DeclarationAbc

if TYPE_CHECKING:
    from .enum_definition import EnumDefinition

from woke.ast.ir.abc import SolidityAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcEnumValue

logger = logging.getLogger(__name__)


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
    _parent: EnumDefinition

    def __init__(self, init: IrInitTuple, value: SolcEnumValue, parent: SolidityAbc):
        super().__init__(init, value, parent)

    def _parse_name_location(self) -> Tuple[int, int]:
        src = self._ast_node.src
        return src.byte_offset, src.byte_offset + src.byte_length

    @property
    def parent(self) -> EnumDefinition:
        """
        Returns:
            Parent IR node.
        """
        return self._parent

    @property
    def canonical_name(self) -> str:
        return f"{self._parent.canonical_name}.{self._name}"

    @property
    def declaration_string(self) -> str:
        return self.name
