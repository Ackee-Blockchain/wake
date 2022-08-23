from functools import lru_cache
from typing import Iterator, Optional, Set, Tuple

from woke.ast.enums import ModifiesStateFlag
from woke.ast.ir.abc import IrAbc, SolidityAbc
from woke.ast.ir.expression.abc import ExpressionAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcIndexRangeAccess


class IndexRangeAccess(ExpressionAbc):
    _ast_node: SolcIndexRangeAccess
    _parent: SolidityAbc  # TODO: make this more specific

    __base_expression: ExpressionAbc
    __start_expression: Optional[ExpressionAbc]
    __end_expression: Optional[ExpressionAbc]

    def __init__(
        self,
        init: IrInitTuple,
        index_range_access: SolcIndexRangeAccess,
        parent: SolidityAbc,
    ):
        super().__init__(init, index_range_access, parent)
        self.__base_expression = ExpressionAbc.from_ast(
            init, index_range_access.base_expression, self
        )

        if index_range_access.start_expression is None:
            self.__start_expression = None
        else:
            self.__start_expression = ExpressionAbc.from_ast(
                init, index_range_access.start_expression, self
            )

        if index_range_access.end_expression is None:
            self.__end_expression = None
        else:
            self.__end_expression = ExpressionAbc.from_ast(
                init, index_range_access.end_expression, self
            )

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        yield from self.__base_expression
        if self.__start_expression is not None:
            yield from self.__start_expression
        if self.__end_expression is not None:
            yield from self.__end_expression

    @property
    def parent(self) -> SolidityAbc:
        return self._parent

    @property
    def base_expression(self) -> ExpressionAbc:
        return self.__base_expression

    @property
    def start_expression(self) -> Optional[ExpressionAbc]:
        return self.__start_expression

    @property
    def end_expression(self) -> Optional[ExpressionAbc]:
        return self.__end_expression

    @property
    def is_ref_to_state_variable(self) -> bool:
        # index range access in only supported for dynamic calldata arrays
        return False

    @property
    @lru_cache(maxsize=None)
    def modifies_state(self) -> Set[Tuple[IrAbc, ModifiesStateFlag]]:
        ret = self.base_expression.modifies_state
        if self.start_expression is not None:
            ret |= self.start_expression.modifies_state
        if self.end_expression is not None:
            ret |= self.end_expression.modifies_state
        return ret
