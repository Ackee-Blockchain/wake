from __future__ import annotations

import re
from collections import deque
from functools import partial
from typing import (
    TYPE_CHECKING,
    Deque,
    FrozenSet,
    Iterator,
    List,
    Optional,
    Set,
    Tuple,
    Union,
)

from ..meta.override_specifier import OverrideSpecifier
from ..reference_resolver import CallbackParams
from ..statement.block import Block
from .abc import DeclarationAbc

if TYPE_CHECKING:
    from .abc import ReferencingNodesUnion
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
    _child_modifiers: Set[ModifierDefinition]

    __body: Optional[Block]
    __implemented: bool
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
        self._child_modifiers = set()

        self.__body = Block(init, modifier.body, self) if modifier.body else None
        self.__implemented = self.__body is not None
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
        self._reference_resolver.register_post_process_callback(self.__post_process)

    def __post_process(self, callback_params: CallbackParams):
        if self.base_modifiers is not None:
            base_modifiers = self.base_modifiers
            for base_modifier in base_modifiers:
                base_modifier._child_modifiers.add(self)
            self._reference_resolver.register_destroy_callback(
                self.file, partial(self.__destroy, base_modifiers)
            )

    def __destroy(self, base_modifiers: Tuple[ModifierDefinition]) -> None:
        for base_modifier in base_modifiers:
            base_modifier._child_modifiers.remove(self)

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

    def get_all_references(
        self, include_declarations: bool
    ) -> Iterator[Union[DeclarationAbc, ReferencingNodesUnion]]:
        processed_declarations: Set[ModifierDefinition] = {self}
        declarations_queue: Deque[ModifierDefinition] = deque([self])

        while declarations_queue:
            declaration = declarations_queue.pop()
            if include_declarations:
                yield declaration
            yield from declaration.references

            if declaration.base_modifiers is not None:
                for base_modifier in declaration.base_modifiers:
                    if base_modifier not in processed_declarations:
                        declarations_queue.append(base_modifier)
                        processed_declarations.add(base_modifier)
            for child_modifier in declaration.child_modifiers:
                if child_modifier not in processed_declarations:
                    declarations_queue.append(child_modifier)
                    processed_declarations.add(child_modifier)

    @property
    def parent(self) -> ContractDefinition:
        return self._parent

    @property
    def canonical_name(self) -> str:
        return f"{self._parent.canonical_name}.{self._name}"

    @property
    def body(self) -> Optional[Block]:
        return self.__body

    @property
    def implemented(self) -> bool:
        return self.__implemented

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
    def child_modifiers(self) -> FrozenSet[ModifierDefinition]:
        return frozenset(self._child_modifiers)

    @property
    def documentation(self) -> Optional[StructuredDocumentation]:
        return self.__documentation

    @property
    def overrides(self) -> Optional[OverrideSpecifier]:
        return self.__overrides
