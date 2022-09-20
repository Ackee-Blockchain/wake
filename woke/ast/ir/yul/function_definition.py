from typing import Iterator, List, Optional, Tuple

from ...nodes import YulFunctionDefinition
from ..utils import IrInitTuple
from .abc import YulAbc
from .block import Block
from .typed_name import TypedName


class FunctionDefinition(YulAbc):
    """
    TBD
    """
    _parent: Block
    _body: Block
    _name: str
    _parameters: Optional[List[TypedName]]
    _return_variables: Optional[List[TypedName]]

    def __init__(
        self,
        init: IrInitTuple,
        function_definition: YulFunctionDefinition,
        parent: YulAbc,
    ):
        super().__init__(init, function_definition, parent)
        self._body = Block(init, function_definition.body, self)
        self._name = function_definition.name
        if function_definition.parameters is None:
            self._parameters = None
        else:
            self._parameters = [
                TypedName(init, parameter, self)
                for parameter in function_definition.parameters
            ]
        if function_definition.return_variables is None:
            self._return_variables = None
        else:
            self._return_variables = [
                TypedName(init, return_variable, self)
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
    def parent(self) -> Block:
        return self._parent

    @property
    def body(self) -> Block:
        return self._body

    @property
    def name(self) -> str:
        return self._name

    @property
    def parameters(self) -> Optional[Tuple[TypedName]]:
        if self._parameters is None:
            return None
        return tuple(self._parameters)

    @property
    def return_variables(self) -> Optional[Tuple[TypedName]]:
        if self._return_variables is None:
            return None
        return tuple(self._return_variables)
