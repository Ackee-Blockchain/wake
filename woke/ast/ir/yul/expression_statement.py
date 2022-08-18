from __future__ import annotations

from typing import TYPE_CHECKING, Iterator, Union

from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import (
    YulExpressionStatement,
    YulFunctionCall,
    YulIdentifier,
    YulLiteral,
)

from .abc import YulAbc
from .function_call import FunctionCall
from .identifier import Identifier
from .literal import Literal

if TYPE_CHECKING:
    from .block import Block


class ExpressionStatement(YulAbc):
    _parent: Block
    __expression: Union[FunctionCall, Identifier, Literal]

    def __init__(
        self,
        init: IrInitTuple,
        expression_statement: YulExpressionStatement,
        parent: YulAbc,
    ):
        super().__init__(init, expression_statement, parent)
        if isinstance(expression_statement.expression, YulFunctionCall):
            self.__expression = FunctionCall(
                init, expression_statement.expression, self
            )
        elif isinstance(expression_statement.expression, YulIdentifier):
            self.__expression = Identifier(init, expression_statement.expression, self)
        elif isinstance(expression_statement.expression, YulLiteral):
            self.__expression = Literal(init, expression_statement.expression, self)
        else:
            assert False, f"Unexpected type: {type(expression_statement.expression)}"

    def __iter__(self) -> Iterator[YulAbc]:
        yield self
        yield from self.__expression

    @property
    def parent(self) -> Block:
        return self._parent

    @property
    def expression(self) -> Union[FunctionCall, Identifier, Literal]:
        return self.__expression
