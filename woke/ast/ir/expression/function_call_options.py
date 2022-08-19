from functools import lru_cache, reduce
from operator import or_
from typing import Iterator, List, Tuple

from woke.ast.enums import ModifiesStateFlag
from woke.ast.ir.abc import IrAbc, SolidityAbc
from woke.ast.ir.expression.abc import ExpressionAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcFunctionCallOptions


class FunctionCallOptions(ExpressionAbc):
    _ast_node: SolcFunctionCallOptions
    _parent: SolidityAbc  # TODO: make this more specific

    __expression: ExpressionAbc
    __names: List[str]
    __options: List[ExpressionAbc]

    def __init__(
        self,
        init: IrInitTuple,
        function_call_options: SolcFunctionCallOptions,
        parent: SolidityAbc,
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

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        yield from self.__expression
        for option in self.__options:
            yield from option

    @property
    def parent(self) -> SolidityAbc:
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

    @property
    def is_ref_to_state_variable(self) -> bool:
        return False

    @property
    @lru_cache(maxsize=None)
    def modifies_state(self) -> ModifiesStateFlag:
        ret = self.expression.modifies_state | reduce(
            or_,
            (option.modifies_state for option in self.options),
            ModifiesStateFlag(0),
        )
        if "value" in self.names:
            ret |= ModifiesStateFlag.SENDS_ETHER
        return ret
