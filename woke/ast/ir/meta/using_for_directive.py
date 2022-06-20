from __future__ import annotations

from typing import TYPE_CHECKING, Union

from woke.ast.ir.meta.identifier_path import IdentifierPath
from woke.ast.ir.type_name.abc import TypeNameAbc
from woke.ast.ir.type_name.user_defined_type_name import UserDefinedTypeName
from woke.ast.ir.utils import IrInitTuple

if TYPE_CHECKING:
    from woke.ast.ir.declaration.contract_definition import ContractDefinition

from woke.ast.ir.abc import IrAbc
from woke.ast.nodes import (
    SolcIdentifierPath,
    SolcUserDefinedTypeName,
    SolcUsingForDirective,
)


class UsingForDirective(IrAbc):
    _ast_node: SolcUsingForDirective
    _parent: ContractDefinition

    __library_name: Union[IdentifierPath, UserDefinedTypeName]
    __type_name: TypeNameAbc

    def __init__(
        self,
        init: IrInitTuple,
        using_for_directive: SolcUsingForDirective,
        parent: ContractDefinition,
    ):
        super().__init__(init, using_for_directive, parent)
        if isinstance(using_for_directive.library_name, SolcUserDefinedTypeName):
            self.__library_name = UserDefinedTypeName(
                init, using_for_directive.library_name, self
            )
        elif isinstance(using_for_directive.library_name, SolcIdentifierPath):
            self.__library_name = IdentifierPath(
                init, using_for_directive.library_name, self
            )
        self.__type_name = TypeNameAbc.from_ast(
            init, using_for_directive.type_name, self
        )

    @property
    def parent(self) -> ContractDefinition:
        return self._parent

    @property
    def library_name(self) -> Union[IdentifierPath, UserDefinedTypeName]:
        return self.__library_name

    @property
    def type_name(self) -> TypeNameAbc:
        return self.__type_name
