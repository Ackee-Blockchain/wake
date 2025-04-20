from __future__ import annotations

import weakref
from typing import TYPE_CHECKING

from .abc import YulStatementAbc

if TYPE_CHECKING:
    from .block import YulBlock


class YulLeave(YulStatementAbc):
    """
    Leave statement exits the execution of the current function.
    It is analogous to the `return` statement in Solidity, except that it does not accept any arguments to be returned as a return value.
    Instead, it returns the last-assigned values to the return variables of the function (or default values if none were assigned).

    !!! example
        ```solidity
        assembly {
            function foo() {
                leave
                // execution stops here
            }
            foo()
            // execution continue here
        }
        ```
    """

    _parent: weakref.ReferenceType[YulBlock]

    @property
    def parent(self) -> YulBlock:
        """
        Returns:
            Parent IR node.
        """
        return super().parent
