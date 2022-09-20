from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Iterator, Set, Tuple, Union

from woke.ast.enums import ModifiesStateFlag
from woke.ast.ir.abc import IrAbc, SolidityAbc
from woke.ast.ir.expression.function_call import FunctionCall
from woke.ast.ir.statement.abc import StatementAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcEmitStatement

if TYPE_CHECKING:
    from .block import Block
    from .do_while_statement import DoWhileStatement
    from .for_statement import ForStatement
    from .if_statement import IfStatement
    from .unchecked_block import UncheckedBlock
    from .while_statement import WhileStatement


class EmitStatement(StatementAbc):
    """
    !!! example
        `:::solidity emit Transfer(msg.sender, to, amount)` in the following code:
        ```solidity
        function transfer(address to, uint amount) public {
            emit Transfer(msg.sender, to, amount);
        }
        ```
    """

    _ast_node: SolcEmitStatement
    _parent: Union[
        Block,
        DoWhileStatement,
        ForStatement,
        IfStatement,
        UncheckedBlock,
        WhileStatement,
    ]

    _event_call: FunctionCall

    def __init__(self, init: IrInitTuple, emit: SolcEmitStatement, parent: SolidityAbc):
        super().__init__(init, emit, parent)
        self._event_call = FunctionCall(init, emit.event_call, self)

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        yield from self._event_call

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
    def event_call(self) -> FunctionCall:
        """
        !!! example
            ```solidity
            Transfer(msg.sender, to, amount)
            ```
            in the following emit statement:
            ```solidity
            emit Transfer(msg.sender, to, amount)
            ```
        Returns:
            Expression representing the event call.
        """
        return self._event_call

    @property
    @lru_cache(maxsize=2048)
    def modifies_state(self) -> Set[Tuple[IrAbc, ModifiesStateFlag]]:
        return {(self, ModifiesStateFlag.EMITS)} | self.event_call.modifies_state
