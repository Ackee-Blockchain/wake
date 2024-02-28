from __future__ import annotations

from typing import TYPE_CHECKING, Iterator, Set, Tuple, Union

from typing_extensions import Literal

from wake.ir.ast import SolcYulCase

from ..enums import ModifiesStateFlag
from ..utils import IrInitTuple
from .abc import YulAbc
from .block import YulBlock
from .literal import YulLiteral

if TYPE_CHECKING:
    from ..expressions.abc import ExpressionAbc
    from ..statements.abc import StatementAbc
    from .switch import YulSwitch


class YulCase(YulAbc):
    """
    Represents a single case in a [YulSwitch][wake.ir.yul.switch.YulSwitch] statement.

    !!! example
        Lines 4-6, 7-9, and 10-12 in the following example:

        ```solidity linenums="1"
        uint x = foo();
        assembly {
            switch x
            case 0 {
                // ...
            }
            case 1 {
                // ...
            }
            default {
                // ...
            }
        }
        ```
    """

    _parent: YulSwitch
    _body: YulBlock
    _value: Union[Literal["default"], YulLiteral]

    def __init__(self, init: IrInitTuple, case_: SolcYulCase, parent: YulAbc):
        super().__init__(init, case_, parent)
        self._body = YulBlock(init, case_.body, self)
        if case_.value == "default":
            self._value = "default"
        else:
            self._value = YulLiteral(init, case_.value, self)

    def __iter__(self) -> Iterator[YulAbc]:
        yield self
        yield from self._body
        if self._value != "default":
            yield from self._value

    @property
    def parent(self) -> YulSwitch:
        """
        Returns:
            Parent IR node.
        """
        return self._parent

    @property
    def body(self) -> YulBlock:
        """
        Returns:
            Body of the case.
        """
        return self._body

    @property
    def value(self) -> Union[Literal["default"], YulLiteral]:
        """
        May be either a [YulLiteral][wake.ir.yul.literal.YulLiteral] or the string `default`.
        `default` is used for the default case when neither of the cases match. The default case
        is optional.

        Returns:
            Value that is compared to the switch expression.
        """
        return self._value

    @property
    def modifies_state(
        self,
    ) -> Set[Tuple[Union[ExpressionAbc, StatementAbc, YulAbc], ModifiesStateFlag]]:
        return self._body.modifies_state
