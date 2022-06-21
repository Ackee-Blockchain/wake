from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from ..statement.block import Block
from .abc import DeclarationAbc

if TYPE_CHECKING:
    from .contract_definition import ContractDefinition

from woke.ast.enums import Visibility
from woke.ast.ir.abc import IrAbc
from woke.ast.ir.meta.parameter_list import ParameterList
from woke.ast.ir.meta.structured_documentation import StructuredDocumentation
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcModifierDefinition


class ModifierDefinition(DeclarationAbc):
    _ast_node: SolcModifierDefinition
    _parent: ContractDefinition

    __name: str
    __body: Block
    __parameters: ParameterList
    __virtual: bool
    __visibility: Visibility
    # __base_modifiers
    __documentation: Optional[StructuredDocumentation]
    # __overrides: Optional[OverrideSpecifier]

    def __init__(
        self, init: IrInitTuple, modifier: SolcModifierDefinition, parent: IrAbc
    ):
        super().__init__(init, modifier, parent)
        self.__name = modifier.name
        self.__body = Block(init, modifier.body, self)
        self.__parameters = ParameterList(init, modifier.parameters, self)
        self.__virtual = modifier.virtual
        self.__visibility = modifier.visibility
        # self.__base_modifiers = modifier.base_modifiers
        self.__documentation = (
            StructuredDocumentation(init, modifier.documentation, self)
            if modifier.documentation
            else None
        )
        # self.__overrides = OverrideSpecifier(init, modifier.overrides, self) if modifier.overrides else None

    @property
    def parent(self) -> ContractDefinition:
        return self._parent

    @property
    def body(self) -> Block:
        return self.__body

    @property
    def parameters(self) -> ParameterList:
        return self.__parameters

    @property
    def virtual(self) -> bool:
        return self.__virtual

    @property
    def visibility(self) -> Visibility:
        return self.__visibility

    @property
    def documentation(self) -> Optional[StructuredDocumentation]:
        return self.__documentation
