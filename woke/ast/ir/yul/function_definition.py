from typing import List, Optional, Tuple

from ...nodes import YulFunctionDefinition
from ..utils import IrInitTuple
from .abc import YulAbc
from .block import Block
from .typed_name import TypedName


class FunctionDefinition(YulAbc):
    _parent: Block
    __body: Block
    __name: str
    __parameters: Optional[List[TypedName]]
    __return_variables: Optional[List[TypedName]]

    def __init__(
        self,
        init: IrInitTuple,
        function_definition: YulFunctionDefinition,
        parent: YulAbc,
    ):
        super().__init__(init, function_definition, parent)
        self.__body = Block(init, function_definition.body, self)
        self.__name = function_definition.name
        if function_definition.parameters is None:
            self.__parameters = None
        else:
            self.__parameters = [
                TypedName(init, parameter, self)
                for parameter in function_definition.parameters
            ]
        if function_definition.return_variables is None:
            self.__return_variables = None
        else:
            self.__return_variables = [
                TypedName(init, return_variable, self)
                for return_variable in function_definition.return_variables
            ]

    @property
    def parent(self) -> Block:
        return self._parent

    @property
    def body(self) -> Block:
        return self.__body

    @property
    def name(self) -> str:
        return self.__name

    @property
    def parameters(self) -> Optional[Tuple[TypedName]]:
        if self.__parameters is None:
            return None
        return tuple(self.__parameters)

    @property
    def return_variables(self) -> Optional[Tuple[TypedName]]:
        if self.__return_variables is None:
            return None
        return tuple(self.__return_variables)
