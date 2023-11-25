from __future__ import annotations

from functools import lru_cache, partial
from typing import TYPE_CHECKING, Iterator, Optional, Set, Tuple, Union

from wake.ir.abc import IrAbc, SolidityAbc
from wake.ir.ast import AstNodeId, SolcUnaryOperation
from wake.ir.declarations.function_definition import FunctionDefinition
from wake.ir.enums import ModifiesStateFlag, UnaryOpOperator
from wake.ir.expressions.abc import ExpressionAbc
from wake.ir.reference_resolver import CallbackParams
from wake.ir.utils import IrInitTuple

if TYPE_CHECKING:
    from ..statements.abc import StatementAbc
    from ..yul.abc import YulAbc


class UnaryOperation(ExpressionAbc):
    """
    !!! example
        ```solidity
        -x
        ```
    """

    _ast_node: SolcUnaryOperation
    _parent: SolidityAbc

    _operator: UnaryOpOperator
    _prefix: bool
    _sub_expression: ExpressionAbc
    _function_id: Optional[AstNodeId]

    def __init__(
        self,
        init: IrInitTuple,
        unary_operation: SolcUnaryOperation,
        parent: SolidityAbc,
    ):
        super().__init__(init, unary_operation, parent)
        self._operator = unary_operation.operator
        self._prefix = unary_operation.prefix
        self._sub_expression = ExpressionAbc.from_ast(
            init, unary_operation.sub_expression, self
        )
        self._function_id = unary_operation.function
        if self._function_id is not None:
            init.reference_resolver.register_post_process_callback(self._post_process)

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        yield from self._sub_expression

    def _post_process(self, callback_params: CallbackParams):
        function = self.function
        assert function is not None
        function.register_reference(self)
        self._reference_resolver.register_destroy_callback(
            self.source_unit.file, partial(self._destroy, function)
        )

    def _destroy(self, function: FunctionDefinition) -> None:
        function.unregister_reference(self)

    @property
    def parent(self) -> SolidityAbc:
        return self._parent

    @property
    def operator(self) -> UnaryOpOperator:
        """
        Returns:
            Operator of the unary operation.
        """
        return self._operator

    @property
    def prefix(self) -> bool:
        """
        Returns:
            `False` for `++` and `--` operators applied as postfix operators, `True` otherwise.
        """
        return self._prefix

    @property
    def sub_expression(self) -> ExpressionAbc:
        """
        Returns:
            Sub-expression the unary operator is applied to.
        """
        return self._sub_expression

    @property
    def is_ref_to_state_variable(self) -> bool:
        return False

    @property
    @lru_cache(maxsize=2048)
    def modifies_state(
        self,
    ) -> Set[Tuple[Union[ExpressionAbc, StatementAbc, YulAbc], ModifiesStateFlag]]:
        ret = self.sub_expression.modifies_state

        if (
            self.operator
            in {
                UnaryOpOperator.PLUS_PLUS,
                UnaryOpOperator.MINUS_MINUS,
                UnaryOpOperator.DELETE,
            }
            and self.sub_expression.is_ref_to_state_variable
        ):
            ret |= {(self, ModifiesStateFlag.MODIFIES_STATE_VAR)}
        return ret

    @property
    def function(self) -> Optional[FunctionDefinition]:
        """
        Is not `None` if the unary operation operates on user-defined value types with custom operators.

        !!! note
            Only `~` and `-` may be defined as user-defined unary operators.

        !!! example
            The unary operation `:::solidity ~a` on line 11 of the following example references the function `negate` on line 6:
            ```solidity linenums="1"
            pragma solidity ^0.8.19;

            type Int is int;
            using {negate as ~} for Int global;

            function negate(Int a) pure returns (Int) {
                return Int.wrap(-Int.unwrap(a));
            }

            function test(Int a) pure returns (Int) {
                return ~a;
            }
            ```

        Returns:
            Function representing the user-defined operator.
        """
        if self._function_id is None:
            return None
        node = self._reference_resolver.resolve_node(
            self._function_id, self.source_unit.cu_hash
        )
        assert isinstance(node, FunctionDefinition)
        return node
