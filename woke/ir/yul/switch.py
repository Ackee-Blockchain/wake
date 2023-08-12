from __future__ import annotations

from typing import TYPE_CHECKING, Iterator, List, Tuple, Union

from woke.ir.ast import (
    SolcYulFunctionCall,
    SolcYulIdentifier,
    SolcYulLiteral,
    SolcYulSwitch,
)
from woke.ir.utils import IrInitTuple
from woke.ir.yul.abc import YulAbc, YulStatementAbc
from woke.ir.yul.case_statement import YulCase
from woke.ir.yul.function_call import YulFunctionCall
from woke.ir.yul.identifier import YulIdentifier
from woke.ir.yul.literal import YulLiteral

if TYPE_CHECKING:
    from .block import YulBlock


class YulSwitch(YulStatementAbc):
    """
    TBD
    """

    _parent: YulBlock
    _cases: List[YulCase]
    _expression: Union[YulFunctionCall, YulIdentifier, YulLiteral]

    def __init__(self, init: IrInitTuple, switch: SolcYulSwitch, parent: YulAbc):
        super().__init__(init, switch, parent)
        if isinstance(switch.expression, SolcYulFunctionCall):
            self._expression = YulFunctionCall(init, switch.expression, self)
        elif isinstance(switch.expression, SolcYulIdentifier):
            self._expression = YulIdentifier(init, switch.expression, self)
        elif isinstance(switch.expression, SolcYulLiteral):
            self._expression = YulLiteral(init, switch.expression, self)
        else:
            assert False, f"Unexpected type: {type(switch.expression)}"
        self._cases = [YulCase(init, case, self) for case in switch.cases]

    def __iter__(self) -> Iterator[YulAbc]:
        yield self
        yield from self._expression
        for case_ in self._cases:
            yield from case_

    @property
    def parent(self) -> YulBlock:
        return self._parent

    @property
    def cases(self) -> Tuple[YulCase, ...]:
        return tuple(self._cases)

    @property
    def expression(self) -> Union[YulFunctionCall, YulIdentifier, YulLiteral]:
        return self._expression
