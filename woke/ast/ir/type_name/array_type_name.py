from typing import Iterator, Optional, Union

from woke.ast.ir.abc import IrAbc, SolidityAbc
from woke.ast.ir.expression.abc import ExpressionAbc
from woke.ast.ir.type_name.abc import TypeNameAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcArrayTypeName


class ArrayTypeName(TypeNameAbc):
    _ast_node: SolcArrayTypeName
    _parent: SolidityAbc  # TODO: make this more specific

    __base_type: TypeNameAbc
    __length: Optional[ExpressionAbc]

    def __init__(
        self, init: IrInitTuple, array_type_name: SolcArrayTypeName, parent: SolidityAbc
    ):
        super().__init__(init, array_type_name, parent)
        self.__base_type = TypeNameAbc.from_ast(init, array_type_name.base_type, self)
        self.__length = (
            ExpressionAbc.from_ast(init, array_type_name.length, self)
            if array_type_name.length
            else None
        )

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        yield from self.__base_type
        if self.__length is not None:
            yield from self.__length

    @property
    def parent(self) -> SolidityAbc:
        return self._parent

    @property
    def base_type(self) -> TypeNameAbc:
        return self.__base_type

    @property
    def length(self) -> Optional[ExpressionAbc]:
        return self.__length
