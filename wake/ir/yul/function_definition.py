from __future__ import annotations

import weakref
from typing import TYPE_CHECKING, Iterator, List, Optional, Tuple, Union

from wake.ir.ast import SolcYulFunctionDefinition
from wake.utils.decorators import weak_self_lru_cache

from ..utils import IrInitTuple
from .abc import YulAbc, YulStatementAbc
from .block import YulBlock
from .typed_name import YulTypedName

if TYPE_CHECKING:
    from wake.analysis.cfg import ControlFlowGraph


class YulFunctionDefinition(YulStatementAbc):
    """
    Represents a Yul function definition.

    !!! example
        ```solidity
        assembly {
            function foo() -> x, y {
                x := 1
                y := 2
            }
        }
        ```
    """

    _parent: weakref.ReferenceType[YulBlock]
    _body: YulBlock
    _name: str
    _parameters: List[YulTypedName]
    _return_variables: List[YulTypedName]

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
            self._parameters = []
        else:
            self._parameters = [
                YulTypedName(init, parameter, self)
                for parameter in function_definition.parameters
            ]
        if function_definition.return_variables is None:
            self._return_variables = []
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
        """
        Returns:
            Parent IR node.
        """
        return super().parent

    @property
    def children(self) -> Iterator[Union[YulBlock, YulTypedName]]:
        """
        Yields:
            Direct children of this node.
        """
        yield self._body
        yield from self._parameters
        yield from self._return_variables

    @property
    def body(self) -> YulBlock:
        """
        Returns:
            Body of the function.
        """
        return self._body

    @property
    def name(self) -> str:
        """
        Returns:
            Name of the function.
        """
        return self._name

    @property
    def parameters(self) -> Tuple[YulTypedName, ...]:
        """
        Returns:
            Parameters of the function.
        """
        return tuple(self._parameters)

    @property
    def return_variables(self) -> Optional[Tuple[YulTypedName, ...]]:
        """
        Returns:
            Return variables of the function.
        """
        return tuple(self._return_variables)

    @property
    @weak_self_lru_cache(maxsize=64)
    def cfg(self) -> ControlFlowGraph:
        """
        Returns:
            Control flow graph of the function.
        """
        from wake.analysis.cfg import ControlFlowGraph

        return ControlFlowGraph(self)
