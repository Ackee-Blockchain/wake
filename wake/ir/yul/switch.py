from __future__ import annotations

import weakref
from typing import TYPE_CHECKING, Iterator, List, Tuple, Union

from wake.ir.ast import (
    SolcYulFunctionCall,
    SolcYulIdentifier,
    SolcYulLiteral,
    SolcYulSwitch,
)
from wake.ir.utils import IrInitTuple
from wake.ir.yul.abc import YulAbc, YulStatementAbc
from wake.ir.yul.case_ import YulCase
from wake.ir.yul.function_call import YulFunctionCall
from wake.ir.yul.identifier import YulIdentifier
from wake.ir.yul.literal import YulLiteral

if TYPE_CHECKING:
    from .block import YulBlock


class YulSwitch(YulStatementAbc):
    """
    Represents a switch statement with the following structure:

    ```solidity
    switch <expression> {
        <cases>
    }
    ```

    !!! example
        ```solidity
        assembly {
            switch lt(i, 10)
            case 1 {
                // ...
            }
            case 2 {
                // ...
            }
            default {
                // ...
            }
        }
        ```
    """

    _parent: weakref.ReferenceType[YulBlock]
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
        """
        Returns:
            Parent IR node.
        """
        return super().parent

    @property
    def children(
        self,
    ) -> Iterator[Union[YulFunctionCall, YulIdentifier, YulLiteral, YulCase]]:
        """
        Yields:
            Direct children of this node.
        """
        yield self._expression
        yield from self._cases

    @property
    def cases(self) -> Tuple[YulCase, ...]:
        """
        The `default` case is optional.

        Returns:
            Tuple of cases of this switch statement in the order they appear in the source code.
        """
        return tuple(self._cases)

    @property
    def expression(self) -> Union[YulFunctionCall, YulIdentifier, YulLiteral]:
        """
        Returns:
            Expression that is evaluated to determine which case to execute.
        """
        return self._expression
