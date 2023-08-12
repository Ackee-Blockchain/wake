from __future__ import annotations

from typing import Iterator, Union

from woke.ir.ast import (
    SolcYulForLoop,
    SolcYulFunctionCall,
    SolcYulIdentifier,
    SolcYulLiteral,
)

from ..utils import IrInitTuple
from .abc import YulAbc, YulStatementAbc
from .block import YulBlock
from .function_call import YulFunctionCall
from .identifier import YulIdentifier
from .literal import YulLiteral


class YulForLoop(YulStatementAbc):
    """
    TBD
    """

    _parent: YulBlock
    _body: YulBlock
    _condition: Union[YulFunctionCall, YulIdentifier, YulLiteral]
    _post: YulBlock
    _pre: YulBlock

    def __init__(self, init: IrInitTuple, for_loop: SolcYulForLoop, parent: YulAbc):
        super().__init__(init, for_loop, parent)
        self._body = YulBlock(init, for_loop.body, self)
        if isinstance(for_loop.condition, SolcYulFunctionCall):
            self._condition = YulFunctionCall(init, for_loop.condition, self)
        elif isinstance(for_loop.condition, SolcYulIdentifier):
            self._condition = YulIdentifier(init, for_loop.condition, self)
        elif isinstance(for_loop.condition, SolcYulLiteral):
            self._condition = YulLiteral(init, for_loop.condition, self)
        else:
            assert False, f"Unexpected type: {type(for_loop.condition)}"
        self._post = YulBlock(init, for_loop.post, self)
        self._pre = YulBlock(init, for_loop.pre, self)

    def __iter__(self) -> Iterator[YulAbc]:
        yield self
        yield from self._pre
        yield from self._condition
        yield from self._body
        yield from self._post

    @property
    def parent(self) -> YulBlock:
        return self._parent

    @property
    def body(self) -> YulBlock:
        return self._body

    @property
    def condition(self) -> Union[YulFunctionCall, YulIdentifier, YulLiteral]:
        return self._condition

    @property
    def post(self) -> YulBlock:
        return self._post

    @property
    def pre(self) -> YulBlock:
        return self._pre
