from __future__ import annotations

from functools import lru_cache, partial
from typing import TYPE_CHECKING, Iterator, Optional, Set, Tuple, Union

from wake.ir.abc import IrAbc, SolidityAbc
from wake.ir.ast import AstNodeId, SolcBinaryOperation
from wake.ir.enums import BinaryOpOperator, ModifiesStateFlag
from wake.ir.utils import IrInitTuple

from ..declarations.function_definition import FunctionDefinition
from ..reference_resolver import CallbackParams
from .abc import ExpressionAbc

if TYPE_CHECKING:
    from ..statements.abc import StatementAbc
    from ..yul.abc import YulAbc


class BinaryOperation(ExpressionAbc):
    """
    !!! example
        ```solidity
        x + y
        ```
    """

    _ast_node: SolcBinaryOperation
    _parent: SolidityAbc  # TODO: make this more specific

    _left_expression: ExpressionAbc
    _operator: BinaryOpOperator
    _right_expression: ExpressionAbc
    _function_id: Optional[AstNodeId]

    def __init__(
        self,
        init: IrInitTuple,
        binary_operation: SolcBinaryOperation,
        parent: SolidityAbc,
    ):
        super().__init__(init, binary_operation, parent)
        self._operator = binary_operation.operator
        self._left_expression = ExpressionAbc.from_ast(
            init, binary_operation.left_expression, self
        )
        self._right_expression = ExpressionAbc.from_ast(
            init, binary_operation.right_expression, self
        )
        self._function_id = binary_operation.function
        if self._function_id is not None:
            init.reference_resolver.register_post_process_callback(self._post_process)

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        yield from self._left_expression
        yield from self._right_expression

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
    def operator(self) -> BinaryOpOperator:
        """
        Returns:
            Operator of the binary operation.
        """
        return self._operator

    @property
    def left_expression(self) -> ExpressionAbc:
        """
        Returns:
            Left expression of the binary operation.
        """
        return self._left_expression

    @property
    def right_expression(self) -> ExpressionAbc:
        """
        Returns:
            Right expression of the binary operation.
        """
        return self._right_expression

    @property
    def is_ref_to_state_variable(self) -> bool:
        return False

    @property
    @lru_cache(maxsize=2048)
    def modifies_state(
        self,
    ) -> Set[Tuple[Union[ExpressionAbc, StatementAbc, YulAbc], ModifiesStateFlag]]:
        return (
            self.left_expression.modifies_state | self.right_expression.modifies_state
        )

    @property
    def function(self) -> Optional[FunctionDefinition]:
        """
        Is not `None` if the binary operation operates on user-defined value types with custom operators.

        !!! example
            The binary operation `a + b` on line 11 of the following example references the function `add` on line 6:
            ```solidity linenums="1"
            pragma solidity ^0.8.19;

            type Int is int;
            using {add as +} for Int global;

            function add(Int a, Int b) pure returns (Int) {
                return Int.wrap(Int.unwrap(a) + Int.unwrap(b));
            }

            function test(Int a, Int b) pure returns (Int) {
                return a + b; // Equivalent to add(a, b)
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
