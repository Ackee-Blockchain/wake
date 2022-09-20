from __future__ import annotations

from typing import TYPE_CHECKING, Iterator, List, Tuple, Union

from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import YulAssignment, YulFunctionCall, YulIdentifier, YulLiteral

from .abc import YulAbc
from .function_call import FunctionCall
from .identifier import Identifier
from .literal import Literal

if TYPE_CHECKING:
    from .block import Block


class Assignment(YulAbc):
    """
    TBD
    """
    _parent: Block
    _value: Union[FunctionCall, Identifier, Literal]
    _variable_names: List[Identifier]

    def __init__(self, init: IrInitTuple, assignment: YulAssignment, parent: YulAbc):
        super().__init__(init, assignment, parent)
        if isinstance(assignment.value, YulFunctionCall):
            self._value = FunctionCall(init, assignment.value, self)
        elif isinstance(assignment.value, YulIdentifier):
            self._value = Identifier(init, assignment.value, self)
        elif isinstance(assignment.value, YulLiteral):
            self._value = Literal(init, assignment.value, self)
        else:
            assert False, f"Unexpected type: {type(assignment.value)}"
        self._variable_names = [
            Identifier(init, variable_name, self)
            for variable_name in assignment.variable_names
        ]

    def __iter__(self) -> Iterator[YulAbc]:
        yield self
        yield from self._value
        for variable_name in self._variable_names:
            yield from variable_name

    @property
    def parent(self) -> Block:
        return self._parent

    @property
    def value(self) -> Union[FunctionCall, Identifier, Literal]:
        return self._value

    @property
    def variable_names(self) -> Tuple[Identifier]:
        return tuple(self._variable_names)
