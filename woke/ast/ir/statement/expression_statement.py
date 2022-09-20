from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Iterator, Set, Tuple, Union

from woke.ast.enums import ModifiesStateFlag
from woke.ast.ir.abc import IrAbc, SolidityAbc
from woke.ast.ir.expression.abc import ExpressionAbc
from woke.ast.ir.statement.abc import StatementAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcExpressionStatement

from ..expression.assignment import Assignment
from ..expression.binary_operation import BinaryOperation
from ..expression.conditional import Conditional
from ..expression.function_call import FunctionCall
from ..expression.function_call_options import FunctionCallOptions
from ..expression.identifier import Identifier
from ..expression.index_access import IndexAccess
from ..expression.index_range_access import IndexRangeAccess
from ..expression.literal import Literal
from ..expression.member_access import MemberAccess
from ..expression.tuple_expression import TupleExpression
from ..expression.unary_operation import UnaryOperation

if TYPE_CHECKING:
    from .block import Block
    from .do_while_statement import DoWhileStatement
    from .for_statement import ForStatement
    from .if_statement import IfStatement
    from .unchecked_block import UncheckedBlock
    from .while_statement import WhileStatement


class ExpressionStatement(StatementAbc):
    """
    !!! example
        The underlying expression can be:

        - an [Assignment][woke.ast.ir.expression.assignment.Assignment]:
            - `:::solidity i = 1` in line 6,
        - a [BinaryOperation][woke.ast.ir.expression.binary_operation.BinaryOperation]:
            - `:::solidity arr[0] + arr[1]` in line 11,
        - a [Conditional][woke.ast.ir.expression.conditional.Conditional]:
            - `:::solidity arr[i] >= arr[i - 1] ? x++ : x--` in line 7,
        - a [FunctionCall][woke.ast.ir.expression.function_call.FunctionCall]:
            - `:::solidity require(arr.length > 1)` in line 3,
        - a [FunctionCallOptions][woke.ast.ir.expression.function_call_options.FunctionCallOptions]:
            - `:::solidity payable(msg.sender).call{value: 1}` in line 16,
        - an [Identifier][woke.ast.ir.expression.identifier.Identifier]:
            - `:::solidity this` in line 15,
        - an [IndexAccess][woke.ast.ir.expression.index_access.IndexAccess]:
            - `:::solidity arr[0]` in line 9,
        - an [IndexRangeAccess][woke.ast.ir.expression.index_range_access.IndexRangeAccess]:
            - `:::solidity arr[0:1]` in line 10,
        - a [Literal][woke.ast.ir.expression.literal.Literal]:
            - `:::solidity 10` in line 12,
        - a [MemberAccess][woke.ast.ir.expression.member_access.MemberAccess]:
            - `:::solidity arr.length` in line 13,
        - a [TupleExpression][woke.ast.ir.expression.tuple_expression.TupleExpression]:
            - `:::solidity (arr)` in line 14,
        - an [UnaryOperation][woke.ast.ir.expression.unary_operation.UnaryOperation]:
            - `:::solidity i++` in line 6.

        ```solidity linenums="1"
        contract C {
            function foo(uint[] calldata arr) external view {
                require(arr.length > 1);
                uint i;
                int x = 0;
                for (i = 1; i < arr.length; i++)
                    arr[i] >= arr[i - 1] ? x++ : x--;

                arr[0];
                arr[0:1];
                arr[0] + arr[1];
                10;
                arr.length;
                (arr);
                this; // silence state mutability warning without generating bytecode
                payable(msg.sender).call{value: 1};
            }
        }
        ```
    """

    _ast_node: SolcExpressionStatement
    _parent: Union[
        Block,
        DoWhileStatement,
        ForStatement,
        IfStatement,
        UncheckedBlock,
        WhileStatement,
    ]

    __expression: Union[
        Assignment,
        BinaryOperation,
        Conditional,
        FunctionCall,
        FunctionCallOptions,
        Identifier,
        IndexAccess,
        IndexRangeAccess,
        Literal,
        MemberAccess,
        TupleExpression,
        UnaryOperation,
    ]

    def __init__(
        self,
        init: IrInitTuple,
        expression_statement: SolcExpressionStatement,
        parent: SolidityAbc,
    ):
        super().__init__(init, expression_statement, parent)
        expr = ExpressionAbc.from_ast(init, expression_statement.expression, self)
        assert isinstance(
            expr,
            (
                Assignment,
                BinaryOperation,
                Conditional,
                FunctionCall,
                FunctionCallOptions,
                Identifier,
                IndexAccess,
                IndexRangeAccess,
                Literal,
                MemberAccess,
                TupleExpression,
                UnaryOperation,
            ),
        )
        self._expression = expr

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
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
    def expression(
        self,
    ) -> Union[
        Assignment,
        BinaryOperation,
        Conditional,
        FunctionCall,
        FunctionCallOptions,
        Identifier,
        IndexAccess,
        IndexRangeAccess,
        Literal,
        MemberAccess,
        TupleExpression,
        UnaryOperation,
    ]:
        """
        Returns:
            Expression of the expression statement.
        """
        return self._expression

    @property
    @lru_cache(maxsize=2048)
    def modifies_state(self) -> Set[Tuple[IrAbc, ModifiesStateFlag]]:
        return self.expression.modifies_state
