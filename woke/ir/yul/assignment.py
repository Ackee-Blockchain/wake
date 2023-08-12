from __future__ import annotations

from typing import TYPE_CHECKING, Iterator, List, Tuple, Union

from woke.ir.ast import (
    SolcYulAssignment,
    SolcYulFunctionCall,
    SolcYulIdentifier,
    SolcYulLiteral,
)
from woke.ir.utils import IrInitTuple

from .abc import YulAbc, YulStatementAbc
from .function_call import YulFunctionCall
from .identifier import YulIdentifier
from .literal import YulLiteral

if TYPE_CHECKING:
    from .block import YulBlock


class YulAssignment(YulStatementAbc):
    """
    TBD
    """

    _parent: YulBlock
    _value: Union[YulFunctionCall, YulIdentifier, YulLiteral]
    _variable_names: List[YulIdentifier]

    def __init__(
        self, init: IrInitTuple, assignment: SolcYulAssignment, parent: YulAbc
    ):
        super().__init__(init, assignment, parent)
        if isinstance(assignment.value, SolcYulFunctionCall):
            self._value = YulFunctionCall(init, assignment.value, self)
        elif isinstance(assignment.value, SolcYulIdentifier):
            self._value = YulIdentifier(init, assignment.value, self)
        elif isinstance(assignment.value, SolcYulLiteral):
            self._value = YulLiteral(init, assignment.value, self)
        else:
            assert False, f"Unexpected type: {type(assignment.value)}"
        self._variable_names = [
            YulIdentifier(init, variable_name, self)
            for variable_name in assignment.variable_names
        ]

    def __iter__(self) -> Iterator[YulAbc]:
        yield self
        yield from self._value
        for variable_name in self._variable_names:
            yield from variable_name

    @property
    def parent(self) -> YulBlock:
        return self._parent

    @property
    def value(self) -> Union[YulFunctionCall, YulIdentifier, YulLiteral]:
        return self._value

    @property
    def variable_names(self) -> Tuple[YulIdentifier, ...]:
        return tuple(self._variable_names)
