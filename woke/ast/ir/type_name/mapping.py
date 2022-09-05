from __future__ import annotations

from typing import Iterator, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from ..declaration.variable_declaration import VariableDeclaration
    from ..meta.using_for_directive import UsingForDirective
    from .array_type_name import ArrayTypeName

import woke.ast.expression_types as expr
from woke.ast.ir.abc import IrAbc, SolidityAbc
from woke.ast.ir.type_name.abc import TypeNameAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcMapping


class Mapping(TypeNameAbc):
    _ast_node: SolcMapping
    _parent: Union[VariableDeclaration, UsingForDirective, ArrayTypeName, Mapping]

    __key_type: TypeNameAbc
    __value_type: TypeNameAbc

    def __init__(self, init: IrInitTuple, mapping: SolcMapping, parent: SolidityAbc):
        super().__init__(init, mapping, parent)
        self.__key_type = TypeNameAbc.from_ast(init, mapping.key_type, self)
        self.__value_type = TypeNameAbc.from_ast(init, mapping.value_type, self)

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        yield from self.__key_type
        yield from self.__value_type

    @property
    def parent(self) -> Union[VariableDeclaration, UsingForDirective, ArrayTypeName, Mapping]:
        return self._parent

    @property
    def type(self) -> expr.Mapping:
        t = super().type
        assert isinstance(t, expr.Mapping)
        return t

    @property
    def key_type(self) -> TypeNameAbc:
        return self.__key_type

    @property
    def value_type(self) -> TypeNameAbc:
        return self.__value_type
