from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List, Tuple, Union

if TYPE_CHECKING:
    from ..declaration.error_definition import ErrorDefinition
    from ..declaration.event_definition import EventDefinition
    from ..declaration.function_definition import FunctionDefinition
    from ..declaration.modifier_definition import ModifierDefinition
    from ..type_name.function_type_name import FunctionTypeName
    from .try_catch_clause import TryCatchClause

from woke.ast.ir.abc import IrAbc
from woke.ast.ir.declaration.variable_declaration import VariableDeclaration
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcParameterList

logger = logging.getLogger(__name__)


class ParameterList(IrAbc):
    _ast_node: SolcParameterList
    _parent: Union[
        ErrorDefinition,
        EventDefinition,
        FunctionDefinition,
        FunctionTypeName,
        ModifierDefinition,
        TryCatchClause,
    ]

    __parameters: List[VariableDeclaration]

    def __init__(
        self, init: IrInitTuple, parameter_list: SolcParameterList, parent: IrAbc
    ):
        super().__init__(init, parameter_list, parent)

        self.__parameters = []
        for parameter in parameter_list.parameters:
            self.__parameters.append(VariableDeclaration(init, parameter, self))

    @property
    def parent(
        self,
    ) -> Union[
        ErrorDefinition,
        EventDefinition,
        FunctionDefinition,
        FunctionTypeName,
        ModifierDefinition,
        TryCatchClause,
    ]:
        return self._parent

    @property
    def parameters(self) -> Tuple[VariableDeclaration]:
        return tuple(self.__parameters)
