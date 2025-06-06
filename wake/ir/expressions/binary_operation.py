from __future__ import annotations

import weakref
from functools import partial
from typing import Iterator, Optional

from wake.ir.abc import IrAbc, SolidityAbc
from wake.ir.ast import AstNodeId, SolcBinaryOperation
from wake.ir.enums import BinaryOpOperator
from wake.ir.utils import IrInitTuple

from ..declarations.function_definition import FunctionDefinition
from ..reference_resolver import CallbackParams
from .abc import ExpressionAbc


class BinaryOperation(ExpressionAbc):
    """
    !!! example
        ```solidity
        x + y
        ```
    """

    _ast_node: SolcBinaryOperation
    _parent: weakref.ReferenceType[SolidityAbc]  # TODO: make this more specific

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
        return super().parent

    @property
    def children(self) -> Iterator[ExpressionAbc]:
        """
        Yields:
            Direct children of this node.
        """
        yield self._left_expression
        yield self._right_expression

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
