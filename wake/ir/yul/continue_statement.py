from __future__ import annotations

import weakref
from typing import TYPE_CHECKING

from .abc import YulStatementAbc

if TYPE_CHECKING:
    from .block import YulBlock


class YulContinue(YulStatementAbc):
    """
    Continue statement can be used in a body of a [YulForLoop][wake.ir.yul.for_loop.YulForLoop] to skip the rest of the loop body and continue with the next iteration.

    !!! example
        ```solidity
        assembly {
            for { let i := 0 } lt(i, 10) { i := add(i, 1) } {
                // ...
                continue
            }
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
