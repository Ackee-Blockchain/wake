from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Iterator, List, Optional, Tuple

from woke.ir.ast import SolcYulFunctionDefinition

from ..utils import IrInitTuple
from .abc import YulAbc, YulStatementAbc
from .block import YulBlock
from .typed_name import YulTypedName

if TYPE_CHECKING:
    from woke.analysis.cfg import ControlFlowGraph


class YulFunctionDefinition(YulStatementAbc):
    """
    TBD
    """

    _parent: YulBlock
    _body: YulBlock
    _name: str
    _parameters: Optional[List[YulTypedName]]
    _return_variables: Optional[List[YulTypedName]]

    def __init__(
        self,
        init: IrInitTuple,
        function_definition: SolcYulFunctionDefinition,
        parent: YulAbc,
    ):
        super().__init__(init, function_definition, parent)
        self._body = YulBlock(init, function_definition.body, self)
        self._name = function_definition.name
        if function_definition.parameters is None:
            self._parameters = None
        else:
            self._parameters = [
                YulTypedName(init, parameter, self)
                for parameter in function_definition.parameters
            ]
        if function_definition.return_variables is None:
            self._return_variables = None
        else:
            self._return_variables = [
                YulTypedName(init, return_variable, self)
                for return_variable in function_definition.return_variables
            ]

    def __iter__(self) -> Iterator[YulAbc]:
        yield self
        yield from self._body
        if self._parameters is not None:
            for parameter in self._parameters:
                yield from parameter
        if self._return_variables is not None:
            for return_variable in self._return_variables:
                yield from return_variable

    @property
    def parent(self) -> YulBlock:
        return self._parent

    @property
    def body(self) -> YulBlock:
        return self._body

    @property
    def name(self) -> str:
        return self._name

    @property
    def parameters(self) -> Optional[Tuple[YulTypedName, ...]]:
        if self._parameters is None:
            return None
        return tuple(self._parameters)

    @property
    def return_variables(self) -> Optional[Tuple[YulTypedName, ...]]:
        if self._return_variables is None:
            return None
        return tuple(self._return_variables)

    @property
    @lru_cache(maxsize=64)
    def cfg(self) -> ControlFlowGraph:
        from woke.analysis.cfg import ControlFlowGraph

        return ControlFlowGraph(self)
