from __future__ import annotations

import weakref
from typing import Iterator, Optional

from wake.ir.abc import IrAbc, SolidityAbc
from wake.ir.ast import SolcIndexAccess
from wake.ir.expressions.abc import ExpressionAbc
from wake.ir.utils import IrInitTuple
from wake.utils.decorators import weak_self_lru_cache


class IndexAccess(ExpressionAbc):
    """
    Represents an index access to an array, bytes or mapping.
    """

    _ast_node: SolcIndexAccess
    _parent: weakref.ReferenceType[SolidityAbc]  # TODO: make this more specific

    _base_expression: ExpressionAbc
    _index_expression: Optional[ExpressionAbc]

    def __init__(
        self, init: IrInitTuple, index_access: SolcIndexAccess, parent: SolidityAbc
    ):
        super().__init__(init, index_access, parent)
        self._base_expression = ExpressionAbc.from_ast(
            init, index_access.base_expression, self
        )

        if index_access.index_expression is None:
            self._index_expression = None
        else:
            self._index_expression = ExpressionAbc.from_ast(
                init, index_access.index_expression, self
            )

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        yield from self._base_expression
        if self._index_expression is not None:
            yield from self._index_expression

    @property
    def parent(self) -> SolidityAbc:
        return super().parent

    @property
    def children(self) -> Iterator[ExpressionAbc]:
        """
        Yields:
            Direct children of this node.
        """
        yield self._base_expression
        if self._index_expression is not None:
            yield self._index_expression

    @property
    def base_expression(self) -> ExpressionAbc:
        """
        Returns:
            Base expression being indexed.
        """
        return self._base_expression

    @property
    def index_expression(self) -> Optional[ExpressionAbc]:
        """
        !!! example
            Is `None` for `:::solidity uint[]` in the following example:

            ```solidity
            abi.decode(data, (uint[]))
            ```

        Returns:
            Index expression or `None` if the index is not specified.
        """
        return self._index_expression

    @property
    @weak_self_lru_cache(maxsize=2048)
    def is_ref_to_state_variable(self) -> bool:
        return self.base_expression.is_ref_to_state_variable
