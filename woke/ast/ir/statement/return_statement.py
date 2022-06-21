from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from woke.ast.ir.expression.abc import ExpressionAbc

from .abc import StatementAbc

if TYPE_CHECKING:
    from ..meta.parameter_list import ParameterList

from woke.ast.ir.abc import IrAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import AstNodeId, SolcReturn


class Return(StatementAbc):
    _ast_node: SolcReturn
    _parent: IrAbc  # TODO: make this more specific

    __function_return_parameters: Optional[AstNodeId]
    __documentation: Optional[str]
    __expression: Optional[ExpressionAbc]

    def __init__(self, init: IrInitTuple, return_: SolcReturn, parent: IrAbc):
        super().__init__(init, return_, parent)
        self.__function_return_parameters = return_.function_return_parameters
        self.__documentation = return_.documentation
        self.__expression = (
            ExpressionAbc.from_ast(init, return_.expression, self)
            if return_.expression
            else None
        )

    @property
    def parent(self) -> IrAbc:
        return self._parent

    @property
    def function_return_parameters(self) -> Optional[ParameterList]:
        if self.__function_return_parameters is None:
            return None
        node = self._reference_resolver.resolve_node(
            self.__function_return_parameters, self._cu_hash
        )
        assert isinstance(node, ParameterList)
        return node
