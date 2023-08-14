from functools import lru_cache, partial
from typing import Iterator, Optional, Set, Tuple

from woke.ir.abc import IrAbc, SolidityAbc
from woke.ir.ast import AstNodeId, SolcUnaryOperation
from woke.ir.declarations.function_definition import FunctionDefinition
from woke.ir.enums import ModifiesStateFlag, UnaryOpOperator
from woke.ir.expressions.abc import ExpressionAbc
from woke.ir.reference_resolver import CallbackParams
from woke.ir.utils import IrInitTuple


class UnaryOperation(ExpressionAbc):
    """
    TBD
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
            self.file, partial(self._destroy, function)
        )

    def _destroy(self, function: FunctionDefinition) -> None:
        function.unregister_reference(self)

    @property
    def parent(self) -> SolidityAbc:
        return self._parent

    @property
    def operator(self) -> UnaryOpOperator:
        return self._operator

    @property
    def prefix(self) -> bool:
        return self._prefix

    @property
    def sub_expression(self) -> ExpressionAbc:
        return self._sub_expression

    @property
    def is_ref_to_state_variable(self) -> bool:
        return False

    @property
    @lru_cache(maxsize=2048)
    def modifies_state(self) -> Set[Tuple[IrAbc, ModifiesStateFlag]]:
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
        if self._function_id is None:
            return None
        node = self._reference_resolver.resolve_node(self._function_id, self._cu_hash)
        assert isinstance(node, FunctionDefinition)
        return node
