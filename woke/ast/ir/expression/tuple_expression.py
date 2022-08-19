from functools import lru_cache, reduce
from operator import or_
from typing import Iterator, List, Optional, Tuple

from woke.ast.enums import ModifiesStateFlag
from woke.ast.ir.abc import IrAbc, SolidityAbc
from woke.ast.ir.expression.abc import ExpressionAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcTupleExpression


class TupleExpression(ExpressionAbc):
    _ast_node: SolcTupleExpression
    _parent: SolidityAbc  # TODO: make this more specific

    __components: List[Optional[ExpressionAbc]]
    __is_inline_array: bool

    def __init__(
        self,
        init: IrInitTuple,
        tuple_expression: SolcTupleExpression,
        parent: SolidityAbc,
    ):
        super().__init__(init, tuple_expression, parent)
        self.__is_inline_array = tuple_expression.is_inline_array

        self.__components = []
        for component in tuple_expression.components:
            if component is None:
                self.__components.append(None)
            else:
                self.__components.append(ExpressionAbc.from_ast(init, component, self))

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        for component in self.__components:
            if component is not None:
                yield from component

    @property
    def parent(self) -> SolidityAbc:
        return self._parent

    @property
    def is_inline_array(self) -> bool:
        return self.__is_inline_array

    @property
    def components(self) -> Tuple[Optional[ExpressionAbc]]:
        return tuple(self.__components)

    @property
    @lru_cache(maxsize=None)
    def is_ref_to_state_variable(self) -> bool:
        return any(
            component.is_ref_to_state_variable
            for component in self.__components
            if component is not None
        )

    @property
    @lru_cache(maxsize=None)
    def modifies_state(self) -> ModifiesStateFlag:
        return reduce(
            or_,
            (
                component.modifies_state
                for component in self.__components
                if component is not None
            ),
            ModifiesStateFlag(0),
        )
