from __future__ import annotations

from typing import TYPE_CHECKING, Union

from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import YulTypedName

from .abc import YulAbc

if TYPE_CHECKING:
    from .function_definition import FunctionDefinition
    from .variable_declaration import VariableDeclaration


class TypedName(YulAbc):
    """
    TBD
    """
    _parent: Union[FunctionDefinition, VariableDeclaration]
    _name: str
    _type: str

    def __init__(self, init: IrInitTuple, typed_name: YulTypedName, parent: YulAbc):
        super().__init__(init, typed_name, parent)
        self._name = typed_name.name
        self._type = typed_name.type

    @property
    def parent(self) -> Union[FunctionDefinition, VariableDeclaration]:
        return self._parent

    @property
    def name(self) -> str:
        return self._name

    @property
    def type(self) -> str:
        return self._type
