from functools import lru_cache, partial
from typing import Iterator, Optional, Set, Tuple

from woke.ast.enums import BinaryOpOperator, ModifiesStateFlag
from woke.ast.ir.abc import IrAbc, SolidityAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import AstNodeId, SolcBinaryOperation

from ..declaration.function_definition import FunctionDefinition
from ..reference_resolver import CallbackParams
from .abc import ExpressionAbc


class BinaryOperation(ExpressionAbc):
    """
    TBD
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
            self.file, partial(self._destroy, function)
        )

    def _destroy(self, function: FunctionDefinition) -> None:
        function.unregister_reference(self)

    @property
    def parent(self) -> SolidityAbc:
        return self._parent

    @property
    def operator(self) -> BinaryOpOperator:
        return self._operator

    @property
    def left_expression(self) -> ExpressionAbc:
        return self._left_expression

    @property
    def right_expression(self) -> ExpressionAbc:
        return self._right_expression

    @property
    def is_ref_to_state_variable(self) -> bool:
        return False

    @property
    @lru_cache(maxsize=2048)
    def modifies_state(self) -> Set[Tuple[IrAbc, ModifiesStateFlag]]:
        return (
            self.left_expression.modifies_state | self.right_expression.modifies_state
        )

    @property
    def function(self) -> Optional[FunctionDefinition]:
        if self._function_id is None:
            return None
        node = self._reference_resolver.resolve_node(self._function_id, self._cu_hash)
        assert isinstance(node, FunctionDefinition)
        return node
