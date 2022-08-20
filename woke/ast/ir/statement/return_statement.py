from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Iterator, Optional, Union

from woke.ast.ir.expression.abc import ExpressionAbc

from ...enums import ModifiesStateFlag
from .abc import StatementAbc

if TYPE_CHECKING:
    from ..meta.parameter_list import ParameterList

from woke.ast.ir.abc import IrAbc, SolidityAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import AstNodeId, SolcReturn

if TYPE_CHECKING:
    from .block import Block
    from .do_while_statement import DoWhileStatement
    from .for_statement import ForStatement
    from .if_statement import IfStatement
    from .unchecked_block import UncheckedBlock
    from .while_statement import WhileStatement


class Return(StatementAbc):
    _ast_node: SolcReturn
    _parent: Union[
        Block,
        DoWhileStatement,
        ForStatement,
        IfStatement,
        UncheckedBlock,
        WhileStatement,
    ]

    __function_return_parameters: Optional[AstNodeId]
    __documentation: Optional[str]
    __expression: Optional[ExpressionAbc]

    def __init__(self, init: IrInitTuple, return_: SolcReturn, parent: SolidityAbc):
        super().__init__(init, return_, parent)
        self.__function_return_parameters = return_.function_return_parameters
        self.__documentation = return_.documentation
        self.__expression = (
            ExpressionAbc.from_ast(init, return_.expression, self)
            if return_.expression
            else None
        )

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        if self.__expression is not None:
            yield from self.__expression

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
        return self._parent

    @property
    def function_return_parameters(self) -> Optional[ParameterList]:
        from ..meta.parameter_list import ParameterList

        if self.__function_return_parameters is None:
            return None
        node = self._reference_resolver.resolve_node(
            self.__function_return_parameters, self._cu_hash
        )
        assert isinstance(node, ParameterList)
        return node

    @property
    def expression(self) -> Optional[ExpressionAbc]:
        return self.__expression

    @property
    @lru_cache(maxsize=None)
    def modifies_state(self) -> ModifiesStateFlag:
        if self.__expression is None:
            return ModifiesStateFlag(0)
        return self.__expression.modifies_state
