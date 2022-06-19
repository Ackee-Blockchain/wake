import logging
from typing import List, Tuple

from woke.ast.ir.abc import IrAbc
from woke.ast.ir.declaration.variable_declaration import VariableDeclaration
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcParameterList

logger = logging.getLogger(__name__)


class ParameterList(IrAbc):
    _ast_node: SolcParameterList
    # _parent: Union[] TODO to be added later

    __parameters: List[VariableDeclaration]

    def __init__(
        self, init: IrInitTuple, parameter_list: SolcParameterList, parent: IrAbc
    ):
        super().__init__(init, parameter_list, parent)

        self.__parameters = []
        for parameter in parameter_list.parameters:
            self.__parameters.append(VariableDeclaration(init, parameter, self))

    @property
    def parameters(self) -> Tuple[VariableDeclaration]:
        return tuple(self.__parameters)
