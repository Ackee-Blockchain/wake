from __future__ import annotations

from typing import TYPE_CHECKING, Set, Tuple, Union

from ..enums import ModifiesStateFlag
from .abc import YulAbc, YulStatementAbc

if TYPE_CHECKING:
    from ..expressions.abc import ExpressionAbc
    from ..statements.abc import StatementAbc
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
