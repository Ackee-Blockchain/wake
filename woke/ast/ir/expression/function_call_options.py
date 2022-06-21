from typing import List, Tuple

from woke.ast.ir.abc import IrAbc
from woke.ast.ir.expression.abc import ExpressionAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcFunctionCallOptions


class FunctionCallOptions(ExpressionAbc):
    _ast_node: SolcFunctionCallOptions
    _parent: IrAbc  # TODO: make this more specific

    __expression: ExpressionAbc
    __names: List[str]
    __options: List[ExpressionAbc]

    def __init__(
        self,
        init: IrInitTuple,
        function_call_options: SolcFunctionCallOptions,
        parent: IrAbc,
    ):
        super().__init__(init, function_call_options, parent)
        self.__expression = ExpressionAbc.from_ast(
            init, function_call_options.expression, self
        )
        self.__names = list(function_call_options.names)
        self.__options = [
            ExpressionAbc.from_ast(init, option, self)
            for option in function_call_options.options
        ]

    @property
    def parent(self) -> IrAbc:
        return self._parent

    @property
    def expression(self) -> ExpressionAbc:
        return self.__expression

    @property
    def names(self) -> Tuple[str]:
        return tuple(self.__names)

    @property
    def options(self) -> Tuple[ExpressionAbc]:
        return tuple(self.__options)
