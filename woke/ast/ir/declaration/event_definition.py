from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from .abc import DeclarationAbc

if TYPE_CHECKING:
    from .contract_definition import ContractDefinition

from woke.ast.ir.abc import IrAbc
from woke.ast.ir.meta.parameter_list import ParameterList
from woke.ast.ir.meta.structured_documentation import StructuredDocumentation
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcEventDefinition


class EventDefinition(DeclarationAbc):
    _ast_node: SolcEventDefinition
    _parent: ContractDefinition

    __name: str
    __anonymous: bool
    __parameters: ParameterList
    __documentation: Optional[StructuredDocumentation]

    def __init__(self, init: IrInitTuple, event: SolcEventDefinition, parent: IrAbc):
        super().__init__(init, event, parent)
        self.__name = event.name
        self.__anonymous = event.anonymous
        self.__parameters = ParameterList(init, event.parameters, self)
        self.__documentation = (
            StructuredDocumentation(init, event.documentation, self)
            if event.documentation
            else None
        )
        # TODO event selector?

    @property
    def parent(self) -> ContractDefinition:
        return self._parent

    @property
    def anonymous(self) -> bool:
        return self.__anonymous

    @property
    def parameters(self) -> ParameterList:
        return self.__parameters

    @property
    def documentation(self) -> Optional[StructuredDocumentation]:
        return self.__documentation
