from typing import Iterator, Union

from ...nodes import YulForLoop, YulFunctionCall, YulIdentifier, YulLiteral
from ..utils import IrInitTuple
from .abc import YulAbc
from .block import Block
from .function_call import FunctionCall
from .identifier import Identifier
from .literal import Literal


class ForLoop(YulAbc):
    """
    TBD
    """
    _parent: Block
    _body: Block
    _condition: Union[FunctionCall, Identifier, Literal]
    _post: Block
    _pre: Block

    def __init__(self, init: IrInitTuple, for_loop: YulForLoop, parent: YulAbc):
        super().__init__(init, for_loop, parent)
        self._body = Block(init, for_loop.body, self)
        if isinstance(for_loop.condition, YulFunctionCall):
            self._condition = FunctionCall(init, for_loop.condition, self)
        elif isinstance(for_loop.condition, YulIdentifier):
            self._condition = Identifier(init, for_loop.condition, self)
        elif isinstance(for_loop.condition, YulLiteral):
            self._condition = Literal(init, for_loop.condition, self)
        else:
            assert False, f"Unexpected type: {type(for_loop.condition)}"
        self._post = Block(init, for_loop.post, self)
        self._pre = Block(init, for_loop.pre, self)

    def __iter__(self) -> Iterator[YulAbc]:
        yield self
        yield from self._pre
        yield from self._condition
        yield from self._body
        yield from self._post

    @property
    def parent(self) -> Block:
        return self._parent

    @property
    def body(self) -> Block:
        return self._body

    @property
    def condition(self) -> Union[FunctionCall, Identifier, Literal]:
        return self._condition

    @property
    def post(self) -> Block:
        return self._post

    @property
    def pre(self) -> Block:
        return self._pre
