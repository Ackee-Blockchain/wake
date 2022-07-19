import re
from functools import partial
from pathlib import Path
from typing import Optional, Tuple

from intervaltree import IntervalTree

from woke.ast.ir.abc import IrAbc
from woke.ast.ir.declaration.abc import DeclarationAbc
from woke.ast.ir.reference_resolver import CallbackParams, ReferenceResolver
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import AstNodeId, SolcIdentifierPath

IDENTIFIER_RE = re.compile(r"[a-zA-Z$_][a-zA-Z0-9$_]*".encode("utf-8"))


# almost the same as Identifier, but does not have an AST node ID
class IdentifierPathPart:
    __reference_resolver: ReferenceResolver
    __path_referenced_declaration_id: AstNodeId
    __path_index: int
    __referenced_declaration_id: Optional[AstNodeId]
    __cu_hash: bytes
    __file: Path
    __byte_location: Tuple[int, int]
    __name: str

    def __init__(
        self,
        init: IrInitTuple,
        byte_location: Tuple[int, int],
        name: str,
        path_referenced_declaration_id: AstNodeId,
        path_index: int,
    ):
        self.__reference_resolver = init.reference_resolver
        self.__path_referenced_declaration_id = path_referenced_declaration_id
        # zero-based index from the end of the path
        self.__path_index = path_index
        self.__referenced_declaration_id = None
        self.__cu_hash = init.cu.hash
        self.__file = init.file
        self.__byte_location = byte_location
        self.__name = name

        self.__reference_resolver.register_post_process_callback(self.__post_process)

    def __post_process(self, callback_params: CallbackParams):
        referenced_declaration = self.__reference_resolver.resolve_node(
            self.__path_referenced_declaration_id, self.__cu_hash
        )
        for i in range(self.__path_index):
            assert referenced_declaration.parent is not None
            referenced_declaration = referenced_declaration.parent
        assert isinstance(referenced_declaration, DeclarationAbc)

        node_path_order = self.__reference_resolver.get_node_path_order(
            AstNodeId(referenced_declaration.ast_node_id),
            referenced_declaration.cu_hash,
        )
        this_cu_id = self.__reference_resolver.get_ast_id_from_cu_node_path_order(
            node_path_order, self.__cu_hash
        )

        self.__referenced_declaration_id = this_cu_id
        referenced_declaration.register_reference(self)
        self.__reference_resolver.register_destroy_callback(
            self.file, partial(self.__destroy, referenced_declaration)
        )

    def __destroy(self, referenced_declaration: DeclarationAbc) -> None:
        referenced_declaration.unregister_reference(self)

    @property
    def file(self) -> Path:
        return self.__file

    @property
    def byte_location(self) -> Tuple[int, int]:
        return self.__byte_location

    @property
    def name(self) -> str:
        return self.__name

    @property
    def referenced_declaration(self) -> DeclarationAbc:
        assert self.__referenced_declaration_id is not None
        node = self.__reference_resolver.resolve_node(
            self.__referenced_declaration_id, self.__cu_hash
        )
        assert isinstance(node, DeclarationAbc)
        return node


class IdentifierPath(IrAbc):
    _ast_node: SolcIdentifierPath
    _parent: IrAbc  # TODO: make this more specific

    __name: str
    __referenced_declaration_id: AstNodeId
    __parts: IntervalTree

    def __init__(
        self, init: IrInitTuple, identifier_path: SolcIdentifierPath, parent: IrAbc
    ):
        super().__init__(init, identifier_path, parent)
        self.__name = identifier_path.name
        self.__referenced_declaration_id = identifier_path.referenced_declaration
        assert self.__referenced_declaration_id >= 0

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

    @property
    def parent(self) -> IrAbc:
        return self._parent

    @property
    def name(self) -> str:
        return self.__name

    @property
    def identifier_path_parts(self) -> Tuple[IdentifierPathPart, ...]:
        return tuple(interval.data for interval in sorted(self.__parts))

    def identifier_path_part_at(self, byte_offset: int) -> Optional[IdentifierPathPart]:
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
