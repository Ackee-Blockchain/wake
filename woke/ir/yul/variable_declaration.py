from __future__ import annotations

from typing import TYPE_CHECKING, Iterator, List, Optional, Tuple, Union

from woke.ir.ast import (
    SolcYulFunctionCall,
    SolcYulIdentifier,
    SolcYulLiteral,
    SolcYulVariableDeclaration,
)

from ..utils import IrInitTuple
from .abc import YulAbc, YulStatementAbc
from .function_call import YulFunctionCall
from .identifier import YulIdentifier
from .literal import YulLiteral
from .typed_name import YulTypedName

if TYPE_CHECKING:
    from .block import YulBlock


class YulVariableDeclaration(YulStatementAbc):
    """
    TBD
    """

    _parent: YulBlock
    _variables: List[YulTypedName]
    _value: Optional[Union[YulFunctionCall, YulIdentifier, YulLiteral]]

    def __init__(
        self,
        init: IrInitTuple,
        variable_declaration: SolcYulVariableDeclaration,
        parent: YulAbc,
    ):
        super().__init__(init, variable_declaration, parent)
        self._variables = [
            YulTypedName(init, variable, self)
            for variable in variable_declaration.variables
        ]
        if variable_declaration.value is None:
            self._value = None
        elif isinstance(variable_declaration.value, SolcYulFunctionCall):
            self._value = YulFunctionCall(init, variable_declaration.value, self)
        elif isinstance(variable_declaration.value, SolcYulIdentifier):
            self._value = YulIdentifier(init, variable_declaration.value, self)
        elif isinstance(variable_declaration.value, SolcYulLiteral):
            self._value = YulLiteral(init, variable_declaration.value, self)
        else:
            assert False, f"Unexpected type: {type(variable_declaration.value)}"

    def __iter__(self) -> Iterator[YulAbc]:
        yield self
        for variable in self._variables:
            yield from variable
        if self._value is not None:
            yield from self._value

    @property
    def parent(self) -> YulBlock:
        return self._parent

    @property
    def variables(self) -> Tuple[YulTypedName, ...]:
        return tuple(self._variables)

    @property
    def value(self) -> Optional[Union[YulFunctionCall, YulIdentifier, YulLiteral]]:
        return self._value
