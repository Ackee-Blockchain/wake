from __future__ import annotations

from typing import TYPE_CHECKING, Set, Tuple, Union

from ..enums import ModifiesStateFlag
from .abc import YulAbc, YulStatementAbc

if TYPE_CHECKING:
    from ..expressions.abc import ExpressionAbc
    from ..statements.abc import StatementAbc
    from .block import YulBlock


class YulBreak(YulStatementAbc):
    """
    Break statement can be used in a body of a [YulForLoop][wake.ir.yul.for_loop.YulForLoop] to exit the loop early.

    !!! example
        ```solidity
        assembly {
            for { let i := 0 } lt(i, 10) { i := add(i, 1) } {
                // ...
                break
            }
        }
        ```
    """

    _parent: YulBlock

    @property
    def parent(self) -> YulBlock:
        """
        Returns:
            Parent IR node.
        """
        return self._parent

    @property
    def modifies_state(
        self,
    ) -> Set[Tuple[Union[ExpressionAbc, StatementAbc, YulAbc], ModifiesStateFlag]]:
        return set()
