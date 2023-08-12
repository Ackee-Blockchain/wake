from __future__ import annotations

from typing import TYPE_CHECKING, Union

from woke.ir.ast import SolcYulTypedName
from woke.ir.utils import IrInitTuple

from .abc import YulAbc

if TYPE_CHECKING:
    from .function_definition import YulFunctionDefinition
    from .variable_declaration import YulVariableDeclaration


class YulTypedName(YulAbc):
    """
    TBD
    """

    _parent: Union[YulFunctionDefinition, YulVariableDeclaration]
    _name: str
    _type: str

    def __init__(self, init: IrInitTuple, typed_name: SolcYulTypedName, parent: YulAbc):
        super().__init__(init, typed_name, parent)
        self._name = typed_name.name
        self._type = typed_name.type

    @property
    def parent(self) -> Union[YulFunctionDefinition, YulVariableDeclaration]:
        return self._parent

    @property
    def name(self) -> str:
        return self._name

    @property
    def type(self) -> str:
        return self._type
