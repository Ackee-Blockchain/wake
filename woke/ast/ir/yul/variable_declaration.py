from __future__ import annotations

from typing import TYPE_CHECKING, Iterator, List, Optional, Tuple, Union

from ...nodes import YulFunctionCall, YulIdentifier, YulLiteral, YulVariableDeclaration
from ..utils import IrInitTuple
from .abc import YulAbc
from .function_call import FunctionCall
from .identifier import Identifier
from .literal import Literal
from .typed_name import TypedName

if TYPE_CHECKING:
    from .block import Block


class VariableDeclaration(YulAbc):
    _parent: Block
    __variables: List[TypedName]
    __value: Optional[Union[FunctionCall, Identifier, Literal]]

    def __init__(
        self,
        init: IrInitTuple,
        variable_declaration: YulVariableDeclaration,
        parent: YulAbc,
    ):
        super().__init__(init, variable_declaration, parent)
        self.__variables = [
            TypedName(init, variable, self)
            for variable in variable_declaration.variables
        ]
        if variable_declaration.value is None:
            self.__value = None
        elif isinstance(variable_declaration.value, YulFunctionCall):
            self.__value = FunctionCall(init, variable_declaration.value, self)
        elif isinstance(variable_declaration.value, YulIdentifier):
            self.__value = Identifier(init, variable_declaration.value, self)
        elif isinstance(variable_declaration.value, YulLiteral):
            self.__value = Literal(init, variable_declaration.value, self)
        else:
            assert False, f"Unexpected type: {type(variable_declaration.value)}"

    def __iter__(self) -> Iterator[YulAbc]:
        yield self
        for variable in self.__variables:
            yield from variable
        if self.__value is not None:
            yield from self.__value

    @property
    def parent(self) -> Block:
        return self._parent

    @property
    def variables(self) -> Tuple[TypedName]:
        return tuple(self.__variables)

    @property
    def value(self) -> Optional[Union[FunctionCall, Identifier, Literal]]:
        return self.__value
