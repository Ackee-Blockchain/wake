from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Iterator, Optional, Set, Tuple, Union

from wake.ir.abc import IrAbc, SolidityAbc
from wake.ir.ast import SolcIndexRangeAccess
from wake.ir.enums import ModifiesStateFlag
from wake.ir.expressions.abc import ExpressionAbc
from wake.ir.utils import IrInitTuple

if TYPE_CHECKING:
    from ..statements.abc import StatementAbc
    from ..yul.abc import YulAbc


class IndexRangeAccess(ExpressionAbc):
    """
    Represents an index range access to a dynamic calldata array (other types are not currently supported).
    Both start and end indices are optional.

    !!! example
        `:::solidity arr[1:2]` in the following example:
        ```solidity
        function foo(uint[] calldata arr) external {
            arr[1:2];
        }
        ```
    """

    _ast_node: SolcIndexRangeAccess
    _parent: SolidityAbc  # TODO: make this more specific

    _base_expression: ExpressionAbc
    _start_expression: Optional[ExpressionAbc]
    _end_expression: Optional[ExpressionAbc]

    def __init__(
        self,
        init: IrInitTuple,
        index_range_access: SolcIndexRangeAccess,
        parent: SolidityAbc,
    ):
        super().__init__(init, index_range_access, parent)
        self._base_expression = ExpressionAbc.from_ast(
            init, index_range_access.base_expression, self
        )

        if index_range_access.start_expression is None:
            self._start_expression = None
        else:
            self._start_expression = ExpressionAbc.from_ast(
                init, index_range_access.start_expression, self
            )

        if index_range_access.end_expression is None:
            self._end_expression = None
        else:
            self._end_expression = ExpressionAbc.from_ast(
                init, index_range_access.end_expression, self
            )

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        yield from self._base_expression
        if self._start_expression is not None:
            yield from self._start_expression
        if self._end_expression is not None:
            yield from self._end_expression

    @property
    def parent(self) -> SolidityAbc:
        return self._parent

    @property
    def base_expression(self) -> ExpressionAbc:
        """
        Returns:
            Calldata array expression being indexed.
        """
        return self._base_expression

    @property
    def start_expression(self) -> Optional[ExpressionAbc]:
        """
        If not specified, the start index is assumed to be `0`.

        Returns:
            Start expression or `None` if the start index is not specified.
        """
        return self._start_expression

    @property
    def end_expression(self) -> Optional[ExpressionAbc]:
        """
        If not specified, the end index is assumed to be the length of the array.

        Returns:
            End expression or `None` if the end index is not specified.
        """
        return self._end_expression

    @property
    def is_ref_to_state_variable(self) -> bool:
        # index range access in only supported for dynamic calldata arrays
        return False

    @property
    @lru_cache(maxsize=2048)
    def modifies_state(
        self,
    ) -> Set[Tuple[Union[ExpressionAbc, StatementAbc, YulAbc], ModifiesStateFlag]]:
        ret = self.base_expression.modifies_state
        if self.start_expression is not None:
            ret |= self.start_expression.modifies_state
        if self.end_expression is not None:
            ret |= self.end_expression.modifies_state
        return ret
