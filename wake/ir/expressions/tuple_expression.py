from __future__ import annotations

from functools import lru_cache, reduce
from operator import or_
from typing import TYPE_CHECKING, Iterator, List, Optional, Set, Tuple, Union

from wake.ir.abc import IrAbc, SolidityAbc
from wake.ir.ast import SolcTupleExpression
from wake.ir.enums import ModifiesStateFlag
from wake.ir.expressions.abc import ExpressionAbc
from wake.ir.utils import IrInitTuple

if TYPE_CHECKING:
    from ..statements.abc import StatementAbc
    from ..yul.abc import YulAbc


class TupleExpression(ExpressionAbc):
    """
    Represents multiple expressions enclosed in parentheses.

    !!! example
        `:::solidity (uint256, uint256)` in:

        ```solidity
        abi.decode(data, (uint256, uint256))
        ```
    """

    _ast_node: SolcTupleExpression
    _parent: SolidityAbc  # TODO: make this more specific

    _components: List[Optional[ExpressionAbc]]
    _is_inline_array: bool

    def __init__(
        self,
        init: IrInitTuple,
        tuple_expression: SolcTupleExpression,
        parent: SolidityAbc,
    ):
        super().__init__(init, tuple_expression, parent)
        self._is_inline_array = tuple_expression.is_inline_array

        self._components = []
        for component in tuple_expression.components:
            if component is None:
                self._components.append(None)
            else:
                self._components.append(ExpressionAbc.from_ast(init, component, self))

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        for component in self._components:
            if component is not None:
                yield from component

    @property
    def parent(self) -> SolidityAbc:
        return self._parent

    @property
    def is_inline_array(self) -> bool:
        """
        !!! example
            Returns `True` for `:::solidity [2, 3, 5, 7, 11, 13]` in the following example:

            ```solidity
            uint8[6] memory primes = [2, 3, 5, 7, 11, 13];
            ```

        Returns:
            `True` if the tuple expression is an inline array, `False` otherwise.
        """
        return self._is_inline_array

    @property
    def components(self) -> Tuple[Optional[ExpressionAbc], ...]:
        """
        !!! example
            A component may be `None` if it is omitted, for example `:::solidity (success, )` in the following code snippet:

            ```solidity
            bool success;
            (success, ) = target.call{gas: 1000}(data);
            ```

        Returns:
            Tuple of expressions enclosed in parentheses in the order they appear in the source code.
        """
        return tuple(self._components)

    @property
    @lru_cache(maxsize=2048)
    def is_ref_to_state_variable(self) -> bool:
        return any(
            component.is_ref_to_state_variable
            for component in self._components
            if component is not None
        )

    @property
    @lru_cache(maxsize=2048)
    def modifies_state(
        self,
    ) -> Set[Tuple[Union[ExpressionAbc, StatementAbc, YulAbc], ModifiesStateFlag]]:
        return reduce(
            or_,
            (
                component.modifies_state
                for component in self._components
                if component is not None
            ),
            set(),
        )
