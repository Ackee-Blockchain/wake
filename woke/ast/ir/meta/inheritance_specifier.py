from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional, Union

from ..expression.abc import ExpressionAbc
from ..type_name.user_defined_type_name import UserDefinedTypeName
from ..utils import IrInitTuple
from .identifier_path import IdentifierPath

if TYPE_CHECKING:
    from ..declaration.contract_definition import ContractDefinition

from woke.ast.ir.abc import IrAbc
from woke.ast.nodes import (
    SolcIdentifierPath,
    SolcInheritanceSpecifier,
    SolcUserDefinedTypeName,
)


class InheritanceSpecifier(IrAbc):
    _ast_node: SolcInheritanceSpecifier
    _parent: ContractDefinition

    __base_name: Union[IdentifierPath, UserDefinedTypeName]
    __arguments: Optional[List[ExpressionAbc]]

    def __init__(
        self,
        init: IrInitTuple,
        inheritance_specifier: SolcInheritanceSpecifier,
        parent: ContractDefinition,
    ):
        super().__init__(init, inheritance_specifier, parent)

        if isinstance(inheritance_specifier.base_name, SolcIdentifierPath):
            self.__base_name = IdentifierPath(
                init, inheritance_specifier.base_name, self
            )
        elif isinstance(inheritance_specifier.base_name, SolcUserDefinedTypeName):
            self.__base_name = UserDefinedTypeName(
                init, inheritance_specifier.base_name, self
            )

        if inheritance_specifier.arguments is None:
            self.__arguments = None
        else:
            self.__arguments = []
            for argument in inheritance_specifier.arguments:
                self.__arguments.append(ExpressionAbc.from_ast(init, argument, self))

    @property
    def parent(self) -> ContractDefinition:
        return self._parent

    @property
    def base_name(self) -> Union[IdentifierPath, UserDefinedTypeName]:
        return self.__base_name

    @property
    def arguments(self) -> Optional[List[ExpressionAbc]]:
        return self.__arguments
