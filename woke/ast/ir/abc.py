from abc import ABC
from pathlib import Path
from typing import Optional, Tuple

from woke.ast.ir.reference_resolver import ReferenceResolver
from woke.ast.ir.utils.init_tuple import IrInitTuple
from woke.ast.nodes import (
    SolcArrayTypeName,
    SolcElementaryTypeName,
    SolcExpressionUnion,
    SolcFunctionTypeName,
    SolcMapping,
    SolcNode,
    SolcStatementUnion,
    SolcTypeNameUnion,
    SolcUserDefinedTypeName,
)


class IrAbc(ABC):
    _file: Path
    _source: bytes
    _ast_node: SolcNode
    _parent: Optional["IrAbc"]
    _depth: int
    _cu_hash: bytes
    _reference_resolver: ReferenceResolver

    def __init__(
        self, init: IrInitTuple, solc_node: SolcNode, parent: Optional["IrAbc"]
    ):
        self._file = init.file
        self._ast_node = solc_node
        self._parent = parent
        if self._parent is not None:
            self._depth = self._parent.ast_tree_depth + 1
        else:
            self._depth = 0
        self._cu_hash = init.cu.blake2b_digest

        self._reference_resolver = init.reference_resolver
        self._reference_resolver.register_node(self, solc_node.id, self._cu_hash)

        source_start = solc_node.src.byte_offset
        source_end = source_start + solc_node.src.byte_length
        self._source = init.source[source_start:source_end]
        if source_start != source_end:
            init.interval_tree[source_start:source_end] = self

    @property
    def file(self) -> Path:
        return self._file

    @property
    def ast_tree_depth(self) -> int:
        return self._depth

    @property
    def byte_location(self) -> Tuple[int, int]:
        return (
            self._ast_node.src.byte_offset,
            self._ast_node.src.byte_offset + self._ast_node.src.byte_length,
        )


class TypeNameAbc(IrAbc):
    _type_identifier: Optional[str]
    _type_string: Optional[str]

    def __init__(self, init: IrInitTuple, type_name: SolcTypeNameUnion, parent: IrAbc):
        super().__init__(init, type_name, parent)
        self._type_identifier = type_name.type_descriptions.type_identifier
        self._type_string = type_name.type_descriptions.type_string

    @staticmethod
    def from_ast(
        init: IrInitTuple, type_name: SolcTypeNameUnion, parent: IrAbc
    ) -> "TypeNameAbc":
        from woke.ast.ir.type_name.array_type_name import ArrayTypeName
        from woke.ast.ir.type_name.elementary_type_name import ElementaryTypeName
        from woke.ast.ir.type_name.function_type_name import FunctionTypeName
        from woke.ast.ir.type_name.mapping import Mapping
        from woke.ast.ir.type_name.user_defined_type_name import UserDefinedTypeName

        if isinstance(type_name, SolcArrayTypeName):
            return ArrayTypeName(init, type_name, parent)
        elif isinstance(type_name, SolcElementaryTypeName):
            return ElementaryTypeName(init, type_name, parent)
        elif isinstance(type_name, SolcFunctionTypeName):
            return FunctionTypeName(init, type_name, parent)
        elif isinstance(type_name, SolcMapping):
            return Mapping(init, type_name, parent)
        elif isinstance(type_name, SolcUserDefinedTypeName):
            return UserDefinedTypeName(init, type_name, parent)

    @property
    def type_identifier(self) -> Optional[str]:
        return self._type_identifier

    @property
    def type_string(self) -> Optional[str]:
        return self._type_string


class ExpressionAbc(IrAbc):
    def __init__(
        self, init: IrInitTuple, expression: SolcExpressionUnion, parent: IrAbc
    ):
        super().__init__(init, expression, parent)

    @staticmethod
    def from_ast(
        init: IrInitTuple, expression: SolcExpressionUnion, parent: IrAbc
    ) -> "ExpressionAbc":
        ...


class StatementAbc(IrAbc):
    def __init__(self, init: IrInitTuple, statement: SolcStatementUnion, parent: IrAbc):
        super().__init__(init, statement, parent)

    @staticmethod
    def from_ast(
        init: IrInitTuple, statement: SolcStatementUnion, parent: IrAbc
    ) -> "StatementAbc":
        ...
