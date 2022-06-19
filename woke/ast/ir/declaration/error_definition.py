from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Union

from woke.ast.ir.abc import IrAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcErrorDefinition

from ..meta.parameter_list import ParameterList
from ..meta.structured_documentation import StructuredDocumentation

# if TYPE_CHECKING:
# from .contract_definition import ContractDefinition
# from woke.ast.ir.meta.source_unit import SourceUnit



class ErrorDefinition(IrAbc):
    _ast_node: SolcErrorDefinition
    # _parent: Union[ContractDefinition, SourceUnit]

    __name: str
    __parameters: ParameterList
    __documentation: Optional[StructuredDocumentation]

    def __init__(self, init: IrInitTuple, error: SolcErrorDefinition, parent: IrAbc):
        super().__init__(init, error, parent)
        self.__name = error.name
        self.__parameters = ParameterList(init, error.parameters, self)
        self.__documentation = (
            StructuredDocumentation(init, error.documentation, self)
            if error.documentation
            else None
        )

    # @property
    # def parent(self) -> Union[SourceUnit, ContractDefinition]:
    # return self._parent

    @property
    def name(self) -> str:
        return self.__name

    @property
    def parameters(self) -> ParameterList:
        return self.__parameters

    @property
    def documentation(self) -> Optional[StructuredDocumentation]:
        return self.__documentation
