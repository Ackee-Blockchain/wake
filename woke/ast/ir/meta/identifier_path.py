from __future__ import annotations

import re
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Tuple, Union

if TYPE_CHECKING:
    from .inheritance_specifier import InheritanceSpecifier
    from .modifier_invocation import ModifierInvocation
    from .override_specifier import OverrideSpecifier
    from .using_for_directive import UsingForDirective
    from ..type_name.user_defined_type_name import UserDefinedTypeName

from intervaltree import IntervalTree

from woke.ast.ir.abc import SolidityAbc
from woke.ast.ir.declaration.abc import DeclarationAbc
from woke.ast.ir.reference_resolver import CallbackParams, ReferenceResolver
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import AstNodeId, SolcIdentifierPath

IDENTIFIER_RE = re.compile(r"[a-zA-Z$_][a-zA-Z0-9$_]*".encode("utf-8"))


class IdentifierPathPart:
    """
    A class representing a part of an identifier path. Is almost the same as [Identifier][woke.ast.ir.expression.identifier.Identifier], but it is not generated in the AST output of the compiler and so it is not an IR node.
    """

    _reference_resolver: ReferenceResolver
    _underlying_node: Union[IdentifierPath, UserDefinedTypeName]
    _path_referenced_declaration_id: AstNodeId
    _path_index: int
    _referenced_declaration_id: Optional[AstNodeId]
    _cu_hash: bytes
    _file: Path
    _byte_location: Tuple[int, int]
    _name: str

    def __init__(
        self,
        underlying_node: Union[IdentifierPath, UserDefinedTypeName],
        init: IrInitTuple,
        byte_location: Tuple[int, int],
        name: str,
        path_referenced_declaration_id: AstNodeId,
        path_index: int,
    ):
        self._underlying_node = underlying_node
        self._reference_resolver = init.reference_resolver
        self._path_referenced_declaration_id = path_referenced_declaration_id
        # zero-based index from the end of the path
        self._path_index = path_index
        self._referenced_declaration_id = None
        self._cu_hash = init.cu.hash
        self._file = init.file
        self._byte_location = byte_location
        self._name = name

        self._reference_resolver.register_post_process_callback(self._post_process)

    def _post_process(self, callback_params: CallbackParams):
        referenced_declaration = self._reference_resolver.resolve_node(
            self._path_referenced_declaration_id, self._cu_hash
        )
        for i in range(self._path_index):
            assert referenced_declaration.parent is not None
            referenced_declaration = referenced_declaration.parent
        assert isinstance(referenced_declaration, DeclarationAbc)

        node_path_order = self._reference_resolver.get_node_path_order(
            AstNodeId(referenced_declaration.ast_node_id),
            referenced_declaration.cu_hash,
        )
        this_cu_id = self._reference_resolver.get_ast_id_from_cu_node_path_order(
            node_path_order, self._cu_hash
        )

        self._referenced_declaration_id = this_cu_id
        referenced_declaration.register_reference(self)
        self._reference_resolver.register_destroy_callback(
            self.file, partial(self._destroy, referenced_declaration)
        )

    def _destroy(self, referenced_declaration: DeclarationAbc) -> None:
        referenced_declaration.unregister_reference(self)

    @property
    def underlying_node(self) -> Union[IdentifierPath, UserDefinedTypeName]:
        """
        Returns:
            Underlying IR node (parent) of this identifier path part.
        """
        return self._underlying_node

    @property
    def file(self) -> Path:
        """
        The absolute path to the source file that contains the parent IR node of this identifier path part.
        Returns:
            Absolute path to the file containing this identifier path part.
        """
        return self._file

    @property
    def byte_location(self) -> Tuple[int, int]:
        """
        The start and end byte offsets of this identifier path part in the source file. `{node}.byte_location[0]` is the start byte offset, `{node}.byte_location[1]` is the end byte offset.

        `{node}.byte_location[1]` is always greater than or equal to `{node}.byte_location[0]`.
        Returns:
            Tuple of the start and end byte offsets of this node in the source file.
        """
        return self._byte_location

    @property
    def name(self) -> str:
        """
        !!! example
            `Contract` or `Event` in `Contract.Event`.
        Returns:
            Name of the identifier path part as it appears in the source code.
        """
        return self._name

    @property
    def referenced_declaration(self) -> DeclarationAbc:
        """
        !!! example
            In the case of `Contract.Struct` [IdentifierPath][woke.ast.ir.meta.identifier_path.IdentifierPath], the referenced declaration of `Struct` is the declaration of the struct `Struct` in the contract `Contract`.
        Returns:
            Declaration referenced by this identifier path part.
        """
        assert self._referenced_declaration_id is not None
        node = self._reference_resolver.resolve_node(
            self._referenced_declaration_id, self._cu_hash
        )
        assert isinstance(node, DeclarationAbc)
        return node


class IdentifierPath(SolidityAbc):
    """
    Identifier path represents a path name of identifiers separated by dots. It was introduced in Solidity 0.8.0 to replace
    [UserDefinedTypeName][woke.ast.ir.type_name.user_defined_type_name.UserDefinedTypeName] in some cases.
    """

    _ast_node: SolcIdentifierPath
    _parent: Union[
        InheritanceSpecifier,
        ModifierInvocation,
        OverrideSpecifier,
        UsingForDirective,
        UserDefinedTypeName,
    ]

    _name: str
    _referenced_declaration_id: AstNodeId
    _parts: IntervalTree

    def __init__(
        self,
        init: IrInitTuple,
        identifier_path: SolcIdentifierPath,
        parent: SolidityAbc,
    ):
        super().__init__(init, identifier_path, parent)
        self._name = identifier_path.name
        self._referenced_declaration_id = identifier_path.referenced_declaration
        assert self._referenced_declaration_id >= 0

        matches = list(IDENTIFIER_RE.finditer(self._source))
        groups_count = len(matches)
        assert groups_count > 0

        self._parts = IntervalTree()
        for i, match in enumerate(matches):
            name = match.group(0).decode("utf-8")
            start = self.byte_location[0] + match.start()
            end = self.byte_location[0] + match.end()
            self._parts[start:end] = IdentifierPathPart(
                self,
                init,
                (start, end),
                name,
                self._referenced_declaration_id,
                groups_count - i - 1,
            )

    @property
    def parent(
        self,
    ) -> Union[
        InheritanceSpecifier,
        ModifierInvocation,
        OverrideSpecifier,
        UsingForDirective,
        UserDefinedTypeName,
    ]:
        """
        Returns:
            Parent IR node.
        """
        return self._parent

    @property
    def name(self) -> str:
        """
        Returns:
            Name (as it appears in the source code) of the user-defined type referenced by this identifier path.
        """
        return self._name

    @property
    def identifier_path_parts(self) -> Tuple[IdentifierPathPart, ...]:
        """
        Returns:
            Parts of the identifier path.
        """
        return tuple(interval.data for interval in sorted(self._parts))

    def identifier_path_part_at(self, byte_offset: int) -> Optional[IdentifierPathPart]:
        """
        Parameters:
            byte_offset: Byte offset in the source code.
        Returns:
            Identifier path part at the given byte offset, if any.
        """
        intervals = self._parts.at(byte_offset)
        assert len(intervals) <= 1
        if len(intervals) == 0:
            return None
        return intervals.pop().data

    @property
    def referenced_declaration(self) -> DeclarationAbc:
        """
        Returns:
            Declaration referenced by this identifier path.
        """
        node = self._reference_resolver.resolve_node(
            self._referenced_declaration_id, self._cu_hash
        )
        assert isinstance(node, DeclarationAbc)
        return node
