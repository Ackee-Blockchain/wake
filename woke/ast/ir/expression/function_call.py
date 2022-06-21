from typing import List, Tuple

from woke.ast.enums import FunctionCallKind
from woke.ast.ir.abc import IrAbc
from woke.ast.ir.expression.abc import ExpressionAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcFunctionCall


class FunctionCall(ExpressionAbc):
    _ast_node: SolcFunctionCall
    _parent: IrAbc  # TODO: make this more specific

    __arguments: List[ExpressionAbc]
    __expression: ExpressionAbc
    __kind: FunctionCallKind
    __names: List[str]
    __try_call: bool

    def __init__(
        self, init: IrInitTuple, function_call: SolcFunctionCall, parent: IrAbc
    ):
        super().__init__(init, function_call, parent)
        self.__kind = function_call.kind
        self.__names = list(function_call.names)
        self.__try_call = function_call.try_call

        self.__expression = ExpressionAbc.from_ast(init, function_call.expression, self)
        self.__arguments = [
            ExpressionAbc.from_ast(init, argument, self)
            for argument in function_call.arguments
        ]

    @property
    def parent(self) -> IrAbc:
        return self._parent

    @property
    def kind(self) -> FunctionCallKind:
        return self.__kind

    @property
    def names(self) -> Tuple[str]:
        return tuple(self.__names)

    @property
    def try_call(self) -> bool:
        return self.__try_call

    @property
    def expression(self) -> ExpressionAbc:
        return self.__expression

    @property
    def arguments(self) -> Tuple[ExpressionAbc]:
        return tuple(self.__arguments)
