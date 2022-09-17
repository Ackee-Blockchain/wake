from functools import lru_cache
from typing import Iterator, Set, Tuple

from woke.ast.enums import ModifiesStateFlag, UnaryOpOperator
from woke.ast.ir.abc import IrAbc, SolidityAbc
from woke.ast.ir.expression.abc import ExpressionAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcUnaryOperation


class UnaryOperation(ExpressionAbc):
    """
    TBD
    """

    _ast_node: SolcUnaryOperation
    _parent: SolidityAbc

    __operator: UnaryOpOperator
    __prefix: bool
    __sub_expression: ExpressionAbc

    def __init__(
        self,
        init: IrInitTuple,
        unary_operation: SolcUnaryOperation,
        parent: SolidityAbc,
    ):
        super().__init__(init, unary_operation, parent)
        self.__operator = unary_operation.operator
        self.__prefix = unary_operation.prefix
        self.__sub_expression = ExpressionAbc.from_ast(
            init, unary_operation.sub_expression, self
        )

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        yield from self.__sub_expression

    @property
    def parent(self) -> SolidityAbc:
        return self._parent

    @property
    def operator(self) -> UnaryOpOperator:
        return self.__operator

    @property
    def prefix(self) -> bool:
        return self.__prefix

    @property
    def sub_expression(self) -> ExpressionAbc:
        return self.__sub_expression

    @property
    def is_ref_to_state_variable(self) -> bool:
        return False

    @property
    @lru_cache(maxsize=None)
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
