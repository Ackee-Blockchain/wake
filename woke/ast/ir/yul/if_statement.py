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
    _body: Block
    _condition: Union[FunctionCall, Identifier, Literal]

    def __init__(self, init: IrInitTuple, if_statement: YulIf, parent: YulAbc):
        super().__init__(init, if_statement, parent)
        self._body = Block(init, if_statement.body, self)
        if isinstance(if_statement.condition, YulFunctionCall):
            self._condition = FunctionCall(init, if_statement.condition, self)
        elif isinstance(if_statement.condition, YulIdentifier):
            self._condition = Identifier(init, if_statement.condition, self)
        elif isinstance(if_statement.condition, YulLiteral):
            self._condition = Literal(init, if_statement.condition, self)
        else:
            assert False, f"Unexpected type: {type(if_statement.condition)}"

    def __iter__(self) -> Iterator[YulAbc]:
        yield self
        yield from self._condition
        yield from self._body

    @property
    def parent(self) -> Block:
        return self._parent

    @property
    def body(self) -> Block:
        return self._body

    @property
    def condition(self) -> Union[FunctionCall, Identifier, Literal]:
        return self._condition
