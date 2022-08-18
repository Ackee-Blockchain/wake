from typing import Iterator, Union

from ...nodes import YulForLoop, YulFunctionCall, YulIdentifier, YulLiteral
from ..utils import IrInitTuple
from .abc import YulAbc
from .block import Block
from .function_call import FunctionCall
from .identifier import Identifier
from .literal import Literal


class ForLoop(YulAbc):
    _parent: Block
    __body: Block
    __condition: Union[FunctionCall, Identifier, Literal]
    __post: Block
    __pre: Block

    def __init__(self, init: IrInitTuple, for_loop: YulForLoop, parent: YulAbc):
        super().__init__(init, for_loop, parent)
        self.__body = Block(init, for_loop.body, self)
        if isinstance(for_loop.condition, YulFunctionCall):
            self.__condition = FunctionCall(init, for_loop.condition, self)
        elif isinstance(for_loop.condition, YulIdentifier):
            self.__condition = Identifier(init, for_loop.condition, self)
        elif isinstance(for_loop.condition, YulLiteral):
            self.__condition = Literal(init, for_loop.condition, self)
        else:
            assert False, f"Unexpected type: {type(for_loop.condition)}"
        self.__post = Block(init, for_loop.post, self)
        self.__pre = Block(init, for_loop.pre, self)

    def __iter__(self) -> Iterator[YulAbc]:
        yield self
        yield from self.__pre
        yield from self.__condition
        yield from self.__body
        yield from self.__post

    @property
    def parent(self) -> Block:
        return self._parent

    @property
    def body(self) -> Block:
        return self.__body

    @property
    def condition(self) -> Union[FunctionCall, Identifier, Literal]:
        return self.__condition

    @property
    def post(self) -> Block:
        return self.__post

    @property
    def pre(self) -> Block:
        return self.__pre
