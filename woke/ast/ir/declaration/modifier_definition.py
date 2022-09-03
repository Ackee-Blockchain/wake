from __future__ import annotations

import re
from collections import deque
from functools import lru_cache, partial
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
    from .contract_definition import ContractDefinition
    from ..expression.identifier import Identifier
    from ..expression.member_access import MemberAccess
    from ..meta.identifier_path import IdentifierPathPart
    from ..statement.inline_assembly import ExternalReference

from woke.ast.enums import Visibility
from woke.ast.ir.abc import IrAbc, SolidityAbc
from woke.ast.ir.meta.parameter_list import ParameterList
from woke.ast.ir.meta.structured_documentation import StructuredDocumentation
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import (
    AstNodeId,
    SolcModifierDefinition,
    SolcStructuredDocumentation,
)


class ModifierDefinition(DeclarationAbc):
    _ast_node: SolcModifierDefinition
    _parent: ContractDefinition
    _child_modifiers: Set[ModifierDefinition]

    __body: Optional[Block]
    __implemented: bool
    __parameters: ParameterList
    __virtual: bool
    __visibility: Visibility
    __base_modifiers: List[AstNodeId]
    __documentation: Optional[Union[StructuredDocumentation, str]]
    __overrides: Optional[OverrideSpecifier]

    def __init__(
        self, init: IrInitTuple, modifier: SolcModifierDefinition, parent: SolidityAbc
    ):
        super().__init__(init, modifier, parent)
        self._child_modifiers = set()

        self.__body = Block(init, modifier.body, self) if modifier.body else None
        self.__implemented = self.__body is not None
        self.__parameters = ParameterList(init, modifier.parameters, self)
        self.__virtual = modifier.virtual
        self.__visibility = modifier.visibility
        self.__base_modifiers = (
            list(modifier.base_modifiers) if modifier.base_modifiers is not None else []
        )
        if modifier.documentation is None:
            self.__documentation = None
        elif isinstance(modifier.documentation, SolcStructuredDocumentation):
            self.__documentation = StructuredDocumentation(
                init, modifier.documentation, self
            )
        elif isinstance(modifier.documentation, str):
            self.__documentation = modifier.documentation
        else:
            raise TypeError(
                f"Unknown type of documentation: {type(modifier.documentation)}"
            )
        self.__overrides = (
            OverrideSpecifier(init, modifier.overrides, self)
            if modifier.overrides
            else None
        )
        self._reference_resolver.register_post_process_callback(self.__post_process)

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        if self.__body is not None:
            yield from self.__body
        yield from self.__parameters
        if isinstance(self.__documentation, StructuredDocumentation):
            yield from self.__documentation
        if self.__overrides is not None:
            yield from self.__overrides

    def __post_process(self, callback_params: CallbackParams):
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
    ) -> Iterator[Union[DeclarationAbc, Identifier, IdentifierPathPart, MemberAccess, ExternalReference]]:
        processed_declarations: Set[ModifierDefinition] = {self}
        declarations_queue: Deque[ModifierDefinition] = deque([self])

        while declarations_queue:
            declaration = declarations_queue.pop()
            if include_declarations:
                yield declaration
            yield from declaration.references

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
    @lru_cache(maxsize=None)
    def declaration_string(self) -> str:
        ret = f"modifier {self._name}"
        ret += (
            f"({', '.join(param.declaration_string for param in self.parameters.parameters)})"
            if len(self.parameters.parameters) > 0
            else ""
        )
        ret += " virtual" if self.virtual else ""
        ret += (
            (
                f" override"
                + (
                    "("
                    + ", ".join(
                        override.source for override in self.overrides.overrides
                    )
                    + ")"
                    if len(self.overrides.overrides) > 0
                    else ""
                )
            )
            if self.overrides is not None
            else ""
        )

        if isinstance(self.documentation, StructuredDocumentation):
            return (
                "/// "
                + "\n///".join(line for line in self.documentation.text.splitlines())
                + "\n"
                + ret
            )
        elif isinstance(self.documentation, str):
            return (
                "/// "
                + "\n///".join(line for line in self.documentation.splitlines())
                + "\n"
                + ret
            )
        else:
            return ret

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
    def base_modifiers(self) -> Tuple[ModifierDefinition]:
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
    def documentation(self) -> Optional[Union[StructuredDocumentation, str]]:
        return self.__documentation

    @property
    def overrides(self) -> Optional[OverrideSpecifier]:
        return self.__overrides
