from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Iterator, Optional, Set, Tuple, Union

from woke.ast.ir.expression.abc import ExpressionAbc

from ...enums import ModifiesStateFlag
from .abc import StatementAbc

if TYPE_CHECKING:
    from ..meta.parameter_list import ParameterList

from woke.ast.ir.abc import IrAbc, SolidityAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import AstNodeId, SolcReturn

if TYPE_CHECKING:
    from .block import Block
    from .do_while_statement import DoWhileStatement
    from .for_statement import ForStatement
    from .if_statement import IfStatement
    from .unchecked_block import UncheckedBlock
    from .while_statement import WhileStatement


class Return(StatementAbc):
    """
    !!! example
        `:::solidity return 1` in the following code:
        ```solidity
        function f() public pure returns(uint) {
            return 1;
        }
        ```
    """

    _ast_node: SolcReturn
    _parent: Union[
        Block,
        DoWhileStatement,
        ForStatement,
        IfStatement,
        UncheckedBlock,
        WhileStatement,
    ]

    _function_return_parameters: Optional[AstNodeId]
    _expression: Optional[ExpressionAbc]

    def __init__(self, init: IrInitTuple, return_: SolcReturn, parent: SolidityAbc):
        super().__init__(init, return_, parent)
        self._function_return_parameters = return_.function_return_parameters
        self._expression = (
            ExpressionAbc.from_ast(init, return_.expression, self)
            if return_.expression
            else None
        )

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        if self._expression is not None:
            yield from self._expression

    @property
    def parent(
        self,
    ) -> Union[
        Block,
        DoWhileStatement,
        ForStatement,
        IfStatement,
        UncheckedBlock,
        WhileStatement,
    ]:
        """
        Returns:
            Parent IR node.
        """
        return self._parent

    @property
    def function_return_parameters(self) -> Optional[ParameterList]:
        """
        !!! example
            Can be `None` if the function does not return anything.
            ```solidity
            function f(uint x) public {
                if (x > 0) {
                    return;
                }
                doSomething(x);
            }
            ```

        Returns:
            Parameter list describing the return parameters of the function (if any).
        """
        from ..meta.parameter_list import ParameterList

        if self._function_return_parameters is None:
            return None
        node = self._reference_resolver.resolve_node(
            self._function_return_parameters, self._cu_hash
        )
        assert isinstance(node, ParameterList)
        return node

    @property
    def expression(self) -> Optional[ExpressionAbc]:
        """
        Returns:
            Expression returned by the return statement, if any.
        """
        return self._expression

    @property
    @lru_cache(maxsize=2048)
    def modifies_state(self) -> Set[Tuple[IrAbc, ModifiesStateFlag]]:
        if self._expression is None:
            return set()
        return self._expression.modifies_state
