from abc import ABC
from pathlib import Path
from typing import Optional

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
        self._source = init.source[
            solc_node.src.byte_offset : solc_node.src.byte_offset
            + solc_node.src.byte_length
        ]

    @property
    def file(self) -> Path:
        return self._file

    @property
    def ast_tree_depth(self) -> int:
        return self._depth


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
        import woke.ast.ir.type_name as ir_type_name

        if isinstance(type_name, SolcArrayTypeName):
            return ir_type_name.ArrayTypeName(init, type_name, parent)
        elif isinstance(type_name, SolcElementaryTypeName):
            return ir_type_name.ElementaryTypeName(init, type_name, parent)
        elif isinstance(type_name, SolcFunctionTypeName):
            return ir_type_name.FunctionTypeName(init, type_name, parent)
        elif isinstance(type_name, SolcMapping):
            return ir_type_name.Mapping(init, type_name, parent)
        elif isinstance(type_name, SolcUserDefinedTypeName):
            return ir_type_name.UserDefinedTypeName(init, type_name, parent)

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
