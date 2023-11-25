from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Iterator, Set, Tuple, Union

from wake.ir.abc import IrAbc, SolidityAbc
from wake.ir.ast import SolcExpressionStatement
from wake.ir.enums import ModifiesStateFlag
from wake.ir.expressions.abc import ExpressionAbc
from wake.ir.statements.abc import StatementAbc
from wake.ir.utils import IrInitTuple

if TYPE_CHECKING:
    from ..yul.abc import YulAbc
    from .block import Block
    from .do_while_statement import DoWhileStatement
    from .for_statement import ForStatement
    from .if_statement import IfStatement
    from .unchecked_block import UncheckedBlock
    from .while_statement import WhileStatement


class ExpressionStatement(StatementAbc):
    """
    !!! example
        The underlying expression can be any expression ([ExpressionAbc][wake.ir.expressions.abc.ExpressionAbc]):

        - an [Assignment][wake.ir.expressions.assignment.Assignment]:
            - `:::solidity i = 1` on line 6,
        - a [BinaryOperation][wake.ir.expressions.binary_operation.BinaryOperation]:
            - `:::solidity arr[0] + arr[1]` on line 11,
        - a [Conditional][wake.ir.expressions.conditional.Conditional]:
            - `:::solidity arr[i] >= arr[i - 1] ? x++ : x--` on line 7,
        - an [ElementaryTypeNameExpression][wake.ir.expressions.elementary_type_name_expression.ElementaryTypeNameExpression]:
            - `:::solidity int` on line 18,
        - a [FunctionCall][wake.ir.expressions.function_call.FunctionCall]:
            - `:::solidity require(arr.length > 1)` on line 3,
        - a [FunctionCallOptions][wake.ir.expressions.function_call_options.FunctionCallOptions]:
            - `:::solidity payable(msg.sender).call{value: 1}` on line 17,
        - an [Identifier][wake.ir.expressions.identifier.Identifier]:
            - `:::solidity this` on line 16,
        - an [IndexAccess][wake.ir.expressions.index_access.IndexAccess]:
            - `:::solidity arr[0]` on line 9,
        - an [IndexRangeAccess][wake.ir.expressions.index_range_access.IndexRangeAccess]:
            - `:::solidity arr[0:1]` on line 10,
        - a [Literal][wake.ir.expressions.literal.Literal]:
            - `:::solidity 10` on line 12,
        - a [MemberAccess][wake.ir.expressions.member_access.MemberAccess]:
            - `:::solidity arr.length` on line 13,
        - a [NewExpression][wake.ir.expressions.new_expression.NewExpression]:
            - `:::solidity new uint[]` on line 14,
        - a [TupleExpression][wake.ir.expressions.tuple_expression.TupleExpression]:
            - `:::solidity (arr)` on line 15,
        - an [UnaryOperation][wake.ir.expressions.unary_operation.UnaryOperation]:
            - `:::solidity i++` on line 6.

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
                new uint[];
                (arr);
                this; // silence state mutability warning without generating bytecode
                payable(msg.sender).call{value: 1};
                int;
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

    __expression: ExpressionAbc

    def __init__(
        self,
        init: IrInitTuple,
        expression_statement: SolcExpressionStatement,
        parent: SolidityAbc,
    ):
        super().__init__(init, expression_statement, parent)
        expr = ExpressionAbc.from_ast(init, expression_statement.expression, self)
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
    ) -> ExpressionAbc:
        """
        Returns:
            Expression of the expression statement.
        """
        return self._expression

    @property
    @lru_cache(maxsize=2048)
    def modifies_state(
        self,
    ) -> Set[Tuple[Union[ExpressionAbc, StatementAbc, YulAbc], ModifiesStateFlag]]:
        return self.expression.modifies_state
