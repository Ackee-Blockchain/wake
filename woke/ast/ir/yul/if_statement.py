from typing import Iterator, Union

from ...nodes import YulFunctionCall, YulIdentifier, YulIf, YulLiteral
from ..utils import IrInitTuple
from .abc import YulAbc
from .block import Block
from .function_call import FunctionCall
from .identifier import Identifier
from .literal import Literal


class If(YulAbc):
    """
    TBD
    """
    _parent: Block
    __body: Block
    __condition: Union[FunctionCall, Identifier, Literal]

    def __init__(self, init: IrInitTuple, if_statement: YulIf, parent: YulAbc):
        super().__init__(init, if_statement, parent)
        self.__body = Block(init, if_statement.body, self)
        if isinstance(if_statement.condition, YulFunctionCall):
            self.__condition = FunctionCall(init, if_statement.condition, self)
        elif isinstance(if_statement.condition, YulIdentifier):
            self.__condition = Identifier(init, if_statement.condition, self)
        elif isinstance(if_statement.condition, YulLiteral):
            self.__condition = Literal(init, if_statement.condition, self)
        else:
            assert False, f"Unexpected type: {type(if_statement.condition)}"

    def __iter__(self) -> Iterator[YulAbc]:
        yield self
        yield from self.__condition
        yield from self.__body

    @property
    def parent(self) -> Block:
        return self._parent

    @property
    def body(self) -> Block:
        return self.__body

    @property
    def condition(self) -> Union[FunctionCall, Identifier, Literal]:
        return self.__condition
