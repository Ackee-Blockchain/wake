from __future__ import annotations

from typing import Iterator, Union

from woke.ir.ast import (
    SolcYulFunctionCall,
    SolcYulIdentifier,
    SolcYulIf,
    SolcYulLiteral,
)

from ..utils import IrInitTuple
from .abc import YulAbc, YulStatementAbc
from .block import YulBlock
from .function_call import YulFunctionCall
from .identifier import YulIdentifier
from .literal import YulLiteral


class YulIf(YulStatementAbc):
    """
    TBD
    """

    _parent: YulBlock
    _body: YulBlock
    _condition: Union[YulFunctionCall, YulIdentifier, YulLiteral]

    def __init__(self, init: IrInitTuple, if_statement: SolcYulIf, parent: YulAbc):
        super().__init__(init, if_statement, parent)
        self._body = YulBlock(init, if_statement.body, self)
        if isinstance(if_statement.condition, SolcYulFunctionCall):
            self._condition = YulFunctionCall(init, if_statement.condition, self)
        elif isinstance(if_statement.condition, SolcYulIdentifier):
            self._condition = YulIdentifier(init, if_statement.condition, self)
        elif isinstance(if_statement.condition, SolcYulLiteral):
            self._condition = YulLiteral(init, if_statement.condition, self)
        else:
            assert False, f"Unexpected type: {type(if_statement.condition)}"

    def __iter__(self) -> Iterator[YulAbc]:
        yield self
        yield from self._condition
        yield from self._body

    @property
    def parent(self) -> YulBlock:
        return self._parent

    @property
    def body(self) -> YulBlock:
        return self._body

    @property
    def condition(self) -> Union[YulFunctionCall, YulIdentifier, YulLiteral]:
        return self._condition
