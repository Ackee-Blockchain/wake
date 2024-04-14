from __future__ import annotations

import re
from bisect import bisect
from collections import deque
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Deque, Optional, Set, Tuple, Union

from ...regex_parser import SoliditySourceParser

if TYPE_CHECKING:
    from .inheritance_specifier import InheritanceSpecifier
    from .modifier_invocation import ModifierInvocation
    from .override_specifier import OverrideSpecifier
    from .source_unit import SourceUnit
    from .using_for_directive import UsingForDirective
    from ..type_names.user_defined_type_name import UserDefinedTypeName

from intervaltree import IntervalTree

from wake.ir.abc import SolidityAbc
from wake.ir.ast import AstNodeId, SolcIdentifierPath
from wake.ir.declarations.abc import DeclarationAbc
from wake.ir.reference_resolver import CallbackParams, ReferenceResolver
from wake.ir.utils import IrInitTuple

IDENTIFIER_RE = re.compile(r"[a-zA-Z$_][a-zA-Z0-9$_]*".encode("utf-8"))


class IdentifierPathPart:
    """
    A class representing a part of an identifier path. Is almost the same as [Identifier][wake.ir.expressions.identifier.Identifier], but it is not generated in the AST output of the compiler and so it is not an IR node.
    """

    _reference_resolver: ReferenceResolver
    _underlying_node: Union[IdentifierPath, UserDefinedTypeName]
    _referenced_declaration_id: Optional[AstNodeId]
    _byte_location: Tuple[int, int]
    _name: str
    _source_unit: SourceUnit

    def __init__(
        self,
        underlying_node: Union[IdentifierPath, UserDefinedTypeName],
        byte_location: Tuple[int, int],
        name: str,
        referenced_declaration_id: AstNodeId,
        reference_resolver: ReferenceResolver,
        source_unit: SourceUnit,
    ):
        self._underlying_node = underlying_node
        self._reference_resolver = reference_resolver
        self._referenced_declaration_id = referenced_declaration_id
        self._byte_location = byte_location
        self._name = name
        self._source_unit = source_unit

        self._reference_resolver.register_post_process_callback(self._post_process)

    def _post_process(self, callback_params: CallbackParams):
        referenced_declaration = self.referenced_declaration
        if isinstance(referenced_declaration, DeclarationAbc):
            referenced_declaration.register_reference(self)
            self._reference_resolver.register_destroy_callback(
                self._source_unit.file, partial(self._destroy, referenced_declaration)
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
    def byte_location(self) -> Tuple[int, int]:
        """

        Returns:
            Tuple of the start and end byte offsets of this node in the source file.
        """
        return self._byte_location

    @property
    def source_unit(self) -> SourceUnit:
        """
        Returns:
            Source unit that contains this node.
        """
        return self._source_unit

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
    def referenced_declaration(self) -> Union[DeclarationAbc, SourceUnit]:
        """
        !!! example
            In the case of `Contract.Struct` [IdentifierPath][wake.ir.meta.identifier_path.IdentifierPath], the referenced declaration of `Struct` is the declaration of the struct `Struct` in the contract `Contract`.
        !!! example
            Can be a [SourceUnit][wake.ir.meta.source_unit.SourceUnit] in the following case:
            ```solidity
            import * as Utils from "./Utils.sol";
            ```

        Returns:
            Declaration referenced by this identifier path part.
        """
        from .source_unit import SourceUnit

        assert self._referenced_declaration_id is not None
        node = self._reference_resolver.resolve_node(
            self._referenced_declaration_id, self._source_unit.cu_hash
        )
        assert isinstance(node, (DeclarationAbc, SourceUnit))
        return node


class IdentifierPath(SolidityAbc):
    """
    Identifier path represents a path name of identifiers separated by dots. It was introduced in Solidity 0.8.0 to replace
    [UserDefinedTypeName][wake.ir.type_names.user_defined_type_name.UserDefinedTypeName] in some cases.
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

        self._reference_resolver.register_post_process_callback(self._post_process)

    def _post_process(self, callback_params: CallbackParams):
        def find_referenced_source_unit(
            searched_name: str, start_source_unit: SourceUnit
        ) -> SourceUnit:
            source_units_queue: Deque[SourceUnit] = deque([start_source_unit])
            processed_source_units: Set[Path] = {start_source_unit.file}
            referenced_declaration = None

            while source_units_queue and referenced_declaration is None:
                source_unit = source_units_queue.popleft()

                for import_ in source_unit.imports:
                    if import_.unit_alias == searched_name:
                        referenced_declaration = callback_params.source_units[
                            import_.imported_file
                        ]
                        break
                    for symbol_alias in import_.symbol_aliases:
                        if symbol_alias.local == searched_name:
                            ref = symbol_alias.foreign.referenced_declaration
                            assert isinstance(ref, SourceUnit)
                            referenced_declaration = ref

                    if referenced_declaration is not None:
                        break

                    if import_.imported_file not in processed_source_units:
                        source_units_queue.append(
                            callback_params.source_units[import_.imported_file]
                        )
                        processed_source_units.add(import_.imported_file)

            assert referenced_declaration is not None
            return referenced_declaration

        from ..meta.source_unit import SourceUnit

        source = bytearray(self._source)
        _, stripped_sums = SoliditySourceParser.strip_comments(source)

        matches = list(IDENTIFIER_RE.finditer(source))
        groups_count = len(matches)
        assert groups_count > 0

        self._parts = IntervalTree()
        start_source_unit = callback_params.source_units[self.source_unit.file]

        ref = self.referenced_declaration
        refs = []
        for _ in range(groups_count):
            refs.append(ref)
            if ref is not None:
                ref = ref.parent

        for match, ref in zip(matches, reversed(refs)):
            name = match.group(0).decode("utf-8")

            if ref is None:
                start_source_unit = find_referenced_source_unit(name, start_source_unit)
                referenced_node = start_source_unit
            elif isinstance(ref, (DeclarationAbc, SourceUnit)):
                referenced_node = ref
            else:
                raise TypeError(
                    f"Unexpected type of referenced declaration: {type(ref)}"
                )

            node_path_order = self._reference_resolver.get_node_path_order(
                AstNodeId(referenced_node.ast_node_id),
                referenced_node.source_unit.cu_hash,
            )
            referenced_node_id = (
                self._reference_resolver.get_ast_id_from_cu_node_path_order(
                    node_path_order, self.source_unit.cu_hash
                )
            )

            if len(stripped_sums) == 0:
                stripped = 0
            else:
                index = bisect([s[0] for s in stripped_sums], match.start())
                if index == 0:
                    stripped = 0
                else:
                    stripped = stripped_sums[index - 1][1]

            start = self.byte_location[0] + match.start() + stripped
            end = self.byte_location[0] + match.end() + stripped
            self._parts[start:end] = IdentifierPathPart(
                self,
                (start, end),
                name,
                referenced_node_id,
                self._reference_resolver,
                self.source_unit,
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
        return tuple(
            interval.data  # pyright: ignore reportGeneralTypeIssues
            for interval in sorted(self._parts)
        )

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
            self._referenced_declaration_id, self.source_unit.cu_hash
        )
        assert isinstance(node, DeclarationAbc)
        return node
