from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Tuple

from intervaltree import IntervalTree

if TYPE_CHECKING:
    from woke.ast.ir.declaration.contract_definition import ContractDefinition

from woke.ast.ir.abc import IrAbc
from woke.ast.ir.declaration.abc import DeclarationAbc
from woke.ast.ir.meta.identifier_path import (
    IDENTIFIER_RE,
    IdentifierPath,
    IdentifierPathPart,
)
from woke.ast.ir.type_name.abc import TypeNameAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import AstNodeId, SolcUserDefinedTypeName


class UserDefinedTypeName(TypeNameAbc):
    _ast_node: SolcUserDefinedTypeName
    _parent: IrAbc  # TODO: make this more specific

    __referenced_declaration_id: AstNodeId
    __contract_scope_id: Optional[AstNodeId]
    __name: Optional[str]
    __path_node: Optional[IdentifierPath]
    __parts: Optional[IntervalTree]

    def __init__(
        self,
        init: IrInitTuple,
        user_defined_type_name: SolcUserDefinedTypeName,
        parent: IrAbc,
    ):
        super().__init__(init, user_defined_type_name, parent)
        self.__name = user_defined_type_name.name
        self.__referenced_declaration_id = user_defined_type_name.referenced_declaration
        assert self.__referenced_declaration_id >= 0
        self.__contract_scope_id = user_defined_type_name.contract_scope
        if user_defined_type_name.path_node is None:
            self.__path_node = None
            matches = list(IDENTIFIER_RE.finditer(self._source))
            groups_count = len(matches)
            assert groups_count > 0

            self.__parts = IntervalTree()
            for i, match in enumerate(matches):
                name = match.group(0).decode("utf-8")
                start = self.byte_location[0] + match.start()
                end = self.byte_location[0] + match.end()
                self.__parts[start:end] = IdentifierPathPart(
                    init,
                    (start, end),
                    name,
                    self.__referenced_declaration_id,
                    groups_count - i - 1,
                )
        else:
            self.__path_node = IdentifierPath(
                init, user_defined_type_name.path_node, self
            )
            self.__parts = None

    @property
    def parent(self) -> IrAbc:
        return self._parent

    @property
    def name(self) -> Optional[str]:
        return self.__name

    @property
    def identifier_path_parts(self) -> Tuple[IdentifierPathPart, ...]:
        if self.__path_node is not None:
            return self.__path_node.identifier_path_parts

        assert self.__parts is not None
        return tuple(interval.data for interval in sorted(self.__parts))

    def identifier_path_part_at(self, byte_offset: int) -> Optional[IdentifierPathPart]:
        if self.__path_node is not None:
            return self.__path_node.identifier_path_part_at(byte_offset)

        assert self.__parts is not None
        intervals = self.__parts.at(byte_offset)
        assert len(intervals) <= 1
        if len(intervals) == 0:
            return None
        return intervals.pop().data

    @property
    def referenced_declaration(self) -> DeclarationAbc:
        node = self._reference_resolver.resolve_node(
            self.__referenced_declaration_id, self._cu_hash
        )
        assert isinstance(node, DeclarationAbc)
        return node

    @property
    def contract_scope(self) -> Optional[ContractDefinition]:
        if self.__contract_scope_id is None:
            return None
        node = self._reference_resolver.resolve_node(
            self.__contract_scope_id, self._cu_hash
        )
        assert isinstance(node, ContractDefinition)
        return node

    @property
    def path_node(self) -> Optional[IdentifierPath]:
        return self.__path_node
