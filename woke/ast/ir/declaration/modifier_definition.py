from __future__ import annotations

import re
from typing import TYPE_CHECKING, List, Optional, Tuple

from ..meta.override_specifier import OverrideSpecifier
from ..statement.block import Block
from .abc import DeclarationAbc

if TYPE_CHECKING:
    from .contract_definition import ContractDefinition

from woke.ast.enums import Visibility
from woke.ast.ir.abc import IrAbc
from woke.ast.ir.meta.parameter_list import ParameterList
from woke.ast.ir.meta.structured_documentation import StructuredDocumentation
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import AstNodeId, SolcModifierDefinition


class ModifierDefinition(DeclarationAbc):
    _ast_node: SolcModifierDefinition
    _parent: ContractDefinition

    __name: str
    __body: Block
    __parameters: ParameterList
    __virtual: bool
    __visibility: Visibility
    __base_modifiers: Optional[List[AstNodeId]]
    __documentation: Optional[StructuredDocumentation]
    __overrides: Optional[OverrideSpecifier]

    def __init__(
        self, init: IrInitTuple, modifier: SolcModifierDefinition, parent: IrAbc
    ):
        super().__init__(init, modifier, parent)
        self.__name = modifier.name
        self.__body = Block(init, modifier.body, self)
        self.__parameters = ParameterList(init, modifier.parameters, self)
        self.__virtual = modifier.virtual
        self.__visibility = modifier.visibility
        self.__base_modifiers = (
            list(modifier.base_modifiers) if modifier.base_modifiers else None
        )
        self.__documentation = (
            StructuredDocumentation(init, modifier.documentation, self)
            if modifier.documentation
            else None
        )
        self.__overrides = (
            OverrideSpecifier(init, modifier.overrides, self)
            if modifier.overrides
            else None
        )

    def _parse_name_location(self) -> Tuple[int, int]:
        IDENTIFIER = r"[a-zA-Z$_][a-zA-Z0-9$_]*"
        MODIFIER_RE = re.compile(
            r"^\s*modifier\s+(?P<name>{identifier})".format(
                identifier=IDENTIFIER
            ).encode("utf-8")
        )

        byte_start = self._ast_node.src.byte_offset
        match = MODIFIER_RE.match(self._source)
        assert match
        return byte_start + match.start("name"), byte_start + match.end("name")

    @property
    def parent(self) -> ContractDefinition:
        return self._parent

    @property
    def body(self) -> Block:
        return self.__body

    @property
    def parameters(self) -> ParameterList:
        return self.__parameters

    @property
    def virtual(self) -> bool:
        return self.__virtual

    @property
    def visibility(self) -> Visibility:
        return self.__visibility

    @property
    def base_modifiers(self) -> Optional[Tuple[ModifierDefinition]]:
        if self.__base_modifiers is None:
            return None
        base_modifiers = []
        for base_modifier_id in self.__base_modifiers:
            base_modifier = self._reference_resolver.resolve_node(
                base_modifier_id, self._cu_hash
            )
            assert isinstance(base_modifier, ModifierDefinition)
            base_modifiers.append(base_modifier)
        return tuple(base_modifiers)

    @property
    def documentation(self) -> Optional[StructuredDocumentation]:
        return self.__documentation

    @property
    def overrides(self) -> Optional[OverrideSpecifier]:
        return self.__overrides
