from __future__ import annotations

from bisect import bisect
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING, Deque, Iterator, Optional, Set, Tuple, Union

from intervaltree import IntervalTree

from wake.ir.types import Contract, Enum, Struct, UserDefinedValueType

from ...regex_parser import SoliditySourceParser
from ..reference_resolver import CallbackParams

if TYPE_CHECKING:
    from ..declarations.variable_declaration import VariableDeclaration
    from ..expressions.new_expression import NewExpression
    from ..meta.inheritance_specifier import InheritanceSpecifier
    from ..meta.override_specifier import OverrideSpecifier
    from ..meta.using_for_directive import UsingForDirective
    from ..meta.source_unit import SourceUnit
    from ..type_names.array_type_name import ArrayTypeName
    from ..type_names.mapping import Mapping

from wake.ir.abc import IrAbc, SolidityAbc
from wake.ir.ast import AstNodeId, SolcUserDefinedTypeName
from wake.ir.declarations.abc import DeclarationAbc
from wake.ir.meta.identifier_path import (
    IDENTIFIER_RE,
    IdentifierPath,
    IdentifierPathPart,
)
from wake.ir.type_names.abc import TypeNameAbc
from wake.ir.utils import IrInitTuple


class UserDefinedTypeName(TypeNameAbc):
    """
    User defined type name represents a name path to a user defined type. Path parts are separated by dots.
    In Solidity 0.8.0 a new IR node ([IdentifierPath][wake.ir.meta.identifier_path.IdentifierPath]) was introduced to replace [UserDefinedTypeName][wake.ir.type_names.user_defined_type_name.UserDefinedTypeName] in some cases.

    !!! example
        A user defined type name can be used:

        - inside a [VariableDeclaration][wake.ir.declarations.variable_declaration.VariableDeclaration]:
            - `:::solidity Interface.Struct` on line 18,
            - `:::solidity Interface.Enum` on line 26,
        - inside a [NewExpression][wake.ir.expressions.new_expression.NewExpression]:
            - `:::solidity Contract` on line 20,
        - inside an [InheritanceSpecifier][wake.ir.meta.inheritance_specifier.InheritanceSpecifier]:
            - `:::solidity Interface` on line 23,
        - inside an [OverrideSpecifier][wake.ir.meta.override_specifier.OverrideSpecifier]:
            - `:::solidity Interface` on line 30,
        - inside a [UsingForDirective][wake.ir.meta.using_for_directive.UsingForDirective]:
            - `:::solidity Lib` on line 24,
            - `:::solidity Interface.Struct` on line 24,
        - inside an [ArrayTypeName][wake.ir.type_names.array_type_name.ArrayTypeName]:
            - `:::solidity Interface.Enum` on line 27,
        - inside a [Mapping][wake.ir.type_names.mapping.Mapping]:
            - both occurrences of `:::solidity Interface.Enum` on line 28.

        ```solidity linenums="1"
        pragma solidity 0.7;

        interface Interface {
            enum Enum {
                READY,
                WAITING
            }

            struct Struct {
                uint a;
            }

            function foo() external;
        }

        library Lib {}

        function tmp(Interface.Struct memory s) {
            s.a = 5;
            new Contract();
        }

        contract Contract is Interface {
            using Lib for Interface.Struct;

            Interface.Enum state;
            Interface.Enum[] states;
            mapping(Interface.Enum => Interface.Enum) map;

            function foo() external override(Interface) {
            }
        }
        ```
    """

    _ast_node: SolcUserDefinedTypeName
    _parent: Union[
        VariableDeclaration,
        NewExpression,
        InheritanceSpecifier,
        OverrideSpecifier,
        UsingForDirective,
        ArrayTypeName,
        Mapping,
    ]

    _referenced_declaration_id: AstNodeId
    _contract_scope_id: Optional[AstNodeId]
    _name: Optional[str]
    _path_node: Optional[IdentifierPath]
    _parts: Optional[IntervalTree]

    def __init__(
        self,
        init: IrInitTuple,
        user_defined_type_name: SolcUserDefinedTypeName,
        parent: SolidityAbc,
    ):
        super().__init__(init, user_defined_type_name, parent)
        self._name = user_defined_type_name.name
        self._referenced_declaration_id = user_defined_type_name.referenced_declaration
        assert self._referenced_declaration_id >= 0
        self._contract_scope_id = user_defined_type_name.contract_scope

        if user_defined_type_name.path_node is None:
            self._path_node = None
            self._reference_resolver.register_post_process_callback(self._post_process)
        else:
            self._path_node = IdentifierPath(
                init, user_defined_type_name.path_node, self
            )
            self._parts = None

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

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        if self._path_node is not None:
            yield from self._path_node

    @property
    def parent(
        self,
    ) -> Union[
        VariableDeclaration,
        NewExpression,
        InheritanceSpecifier,
        OverrideSpecifier,
        UsingForDirective,
        ArrayTypeName,
        Mapping,
    ]:
        """
        Returns:
            Parent IR node.
        """
        return self._parent

    @property
    def type(self) -> Union[Contract, Struct, Enum, UserDefinedValueType]:
        """
        Returns:
            Type description.
        """
        t = super().type
        assert isinstance(t, (Contract, Struct, Enum, UserDefinedValueType))
        return t

    @property
    def name(self) -> str:
        """
        !!! note
            Should be the same as [source][wake.ir.abc.IrAbc.source] and is the same as [path_node.name][wake.ir.meta.identifier_path.IdentifierPath.name] if [path_node][wake.ir.type_names.user_defined_type_name.UserDefinedTypeName.path_node] is not `None`.

        Returns:
            Name of the user defined type as it appears in the source code.
        """
        if self._name is None:
            assert self._path_node is not None
            self._name = self._path_node.name
        return self._name

    @property
    def identifier_path_parts(self) -> Tuple[IdentifierPathPart, ...]:
        """
        Returns:
            Parts of the user defined type name.
        """
        if self._path_node is not None:
            return self._path_node.identifier_path_parts

        assert self._parts is not None
        return tuple(
            interval.data  # pyright: ignore reportGeneralTypeIssues
            for interval in sorted(self._parts)
        )

    def identifier_path_part_at(self, byte_offset: int) -> Optional[IdentifierPathPart]:
        """
        Args:
            byte_offset: Byte offset in the source file.

        Returns:
            Identifier path part at the given byte offset, if any.
        """
        if self._path_node is not None:
            return self._path_node.identifier_path_part_at(byte_offset)

        assert self._parts is not None
        intervals = self._parts.at(byte_offset)
        assert len(intervals) <= 1
        if len(intervals) == 0:
            return None
        return intervals.pop().data

    @property
    def referenced_declaration(self) -> DeclarationAbc:
        """
        Returns:
            Declaration IR node referenced by this user defined type name.
        """
        node = self._reference_resolver.resolve_node(
            self._referenced_declaration_id, self.source_unit.cu_hash
        )
        assert isinstance(node, DeclarationAbc)
        return node

    @property
    def path_node(self) -> Optional[IdentifierPath]:
        """
        Always present since Solidity 0.8.0. If not `None`, it represents the same source code as this node ([byte_location][wake.ir.abc.IrAbc.byte_location] properties are the same) and references the same declaration.

        Returns:
            Identifier path IR node.
        """
        return self._path_node
