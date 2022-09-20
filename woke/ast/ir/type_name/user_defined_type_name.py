from __future__ import annotations

from typing import TYPE_CHECKING, Iterator, Optional, Tuple, Union

from intervaltree import IntervalTree

from ...types import Contract, Enum, Struct, UserDefinedValueType

if TYPE_CHECKING:
    from ..declaration.variable_declaration import VariableDeclaration
    from ..expression.new_expression import NewExpression
    from ..meta.inheritance_specifier import InheritanceSpecifier
    from ..meta.override_specifier import OverrideSpecifier
    from ..meta.using_for_directive import UsingForDirective
    from ..type_name.array_type_name import ArrayTypeName
    from ..type_name.mapping import Mapping

from woke.ast.ir.abc import IrAbc, SolidityAbc
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
    """
    User defined type name represents a name path to a user defined type. Path parts are separated by dots.
    In Solidity 0.8.0 a new IR node ([IdentifierPath][woke.ast.ir.meta.identifier_path.IdentifierPath]) was introduced to replace [UserDefinedTypeName][woke.ast.ir.type_name.user_defined_type_name.UserDefinedTypeName] in some cases.

    !!! example
        A user defined type name can be used:

        - inside a [VariableDeclaration][woke.ast.ir.declaration.variable_declaration.VariableDeclaration]:
            - `:::solidity Interface.Struct` in line 18,
            - `:::solidity Interface.Enum` in line 26,
        - inside a [NewExpression][woke.ast.ir.expression.new_expression.NewExpression]:
            - `:::solidity Contract` in line 20,
        - inside an [InheritanceSpecifier][woke.ast.ir.meta.inheritance_specifier.InheritanceSpecifier]:
            - `:::solidity Interface` in line 23,
        - inside an [OverrideSpecifier][woke.ast.ir.meta.override_specifier.OverrideSpecifier]:
            - `:::solidity Interface` in line 30,
        - inside a [UsingForDirective][woke.ast.ir.meta.using_for_directive.UsingForDirective]:
            - `:::solidity Lib` in line 24,
            - `:::solidity Interface.Struct` in line 24,
        - inside an [ArrayTypeName][woke.ast.ir.type_name.array_type_name.ArrayTypeName]:
            - `:::solidity Interface.Enum` in line 27,
        - inside a [Mapping][woke.ast.ir.type_name.mapping.Mapping]:
            - both occurrences of `:::solidity Interface.Enum` in line 28.

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
        else:
            self._path_node = IdentifierPath(
                init, user_defined_type_name.path_node, self
            )
            self._parts = None

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
            Should be the same as [source][woke.ast.ir.abc.IrAbc.source] and is the same as [path_node.name][woke.ast.ir.meta.identifier_path.IdentifierPath.name] if [path_node][woke.ast.ir.type_name.user_defined_type_name.UserDefinedTypeName.path_node] is not `None`.
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
        return tuple(interval.data for interval in sorted(self._parts))

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
            self._referenced_declaration_id, self._cu_hash
        )
        assert isinstance(node, DeclarationAbc)
        return node

    @property
    def path_node(self) -> Optional[IdentifierPath]:
        """
        Always present since Solidity 0.8.0. If not `None`, it represents the same source code as this node ([byte_location][woke.ast.ir.abc.IrAbc.byte_location] properties are the same) and references the same declaration.
        Returns:
            Identifier path IR node.
        """
        return self._path_node
