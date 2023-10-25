from functools import lru_cache, reduce
from operator import or_
from typing import Iterator, List, Set, Tuple

from woke.ir.abc import IrAbc, SolidityAbc
from woke.ir.ast import SolcFunctionCallOptions
from woke.ir.enums import ModifiesStateFlag
from woke.ir.expressions.abc import ExpressionAbc
from woke.ir.utils import IrInitTuple


class FunctionCallOptions(ExpressionAbc):
    """
    TBD
    """

    _ast_node: SolcFunctionCallOptions
    _parent: SolidityAbc  # TODO: make this more specific

    _expression: ExpressionAbc
    _names: List[str]
    _options: List[ExpressionAbc]

    def __init__(
        self,
        init: IrInitTuple,
        function_call_options: SolcFunctionCallOptions,
        parent: SolidityAbc,
    ):
        super().__init__(init, function_call_options, parent)
        self._expression = ExpressionAbc.from_ast(
            init, function_call_options.expression, self
        )
        self._names = list(function_call_options.names)
        self._options = [
            ExpressionAbc.from_ast(init, option, self)
            for option in function_call_options.options
        ]

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        yield from self._expression
        for option in self._options:
            yield from option

    @property
    def parent(self) -> SolidityAbc:
        return self._parent

    @property
    def expression(self) -> ExpressionAbc:
        return self._expression

    @property
    def names(self) -> Tuple[str, ...]:
        return tuple(self._names)

    @property
    def options(self) -> Tuple[ExpressionAbc, ...]:
        return tuple(self._options)

    @property
    def is_ref_to_state_variable(self) -> bool:
        return False

    @property
    @lru_cache(maxsize=2048)
    def modifies_state(self) -> Set[Tuple[IrAbc, ModifiesStateFlag]]:
        ret = self.expression.modifies_state | reduce(
            or_,
            (option.modifies_state for option in self.options),
            set(),
        )
        if "value" in self.names:
            ret |= {(self, ModifiesStateFlag.SENDS_ETHER)}
        return ret
