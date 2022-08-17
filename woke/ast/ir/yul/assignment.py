from __future__ import annotations

from typing import TYPE_CHECKING, List, Tuple, Union

from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import YulAssignment, YulFunctionCall, YulIdentifier, YulLiteral

from .abc import YulAbc
from .function_call import FunctionCall
from .identifier import Identifier
from .literal import Literal

if TYPE_CHECKING:
    from .block import Block


class Assignment(YulAbc):
    _parent: Block
    __value: Union[FunctionCall, Identifier, Literal]
    __variable_names: List[Identifier]

    def __init__(self, init: IrInitTuple, assignment: YulAssignment, parent: YulAbc):
        super().__init__(init, assignment, parent)
        if isinstance(assignment.value, YulFunctionCall):
            self.__value = FunctionCall(init, assignment.value, self)
        elif isinstance(assignment.value, YulIdentifier):
            self.__value = Identifier(init, assignment.value, self)
        elif isinstance(assignment.value, YulLiteral):
            self.__value = Literal(init, assignment.value, self)
        else:
            assert False, f"Unexpected type: {type(assignment.value)}"
        self.__variable_names = [
            Identifier(init, variable_name, self)
            for variable_name in assignment.variable_names
        ]

    @property
    def parent(self) -> Block:
        return self._parent

    @property
    def value(self) -> Union[FunctionCall, Identifier, Literal]:
        return self.__value

    @property
    def variable_names(self) -> Tuple[Identifier]:
        return tuple(self.__variable_names)
