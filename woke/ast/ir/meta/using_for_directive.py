from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional, Tuple, Union

from woke.ast.ir.meta.identifier_path import IdentifierPath
from woke.ast.ir.type_name.abc import TypeNameAbc
from woke.ast.ir.type_name.user_defined_type_name import UserDefinedTypeName
from woke.ast.ir.utils import IrInitTuple

if TYPE_CHECKING:
    from woke.ast.ir.declaration.contract_definition import ContractDefinition
    from .source_unit import SourceUnit

from woke.ast.ir.abc import IrAbc
from woke.ast.nodes import (
    SolcIdentifierPath,
    SolcUserDefinedTypeName,
    SolcUsingForDirective,
)


class UsingForDirective(IrAbc):
    _ast_node: SolcUsingForDirective
    _parent: Union[ContractDefinition, SourceUnit]

    __functions: Optional[List[IdentifierPath]]
    __library_name: Optional[Union[IdentifierPath, UserDefinedTypeName]]
    __type_name: Optional[TypeNameAbc]

    def __init__(
        self,
        init: IrInitTuple,
        using_for_directive: SolcUsingForDirective,
        parent: Union[ContractDefinition, SourceUnit],
    ):
        super().__init__(init, using_for_directive, parent)

        if using_for_directive.function_list is None:
            self.__functions = None
        else:
            self.__functions = [
                IdentifierPath(init, function.function, self)
                for function in using_for_directive.function_list
            ]

        if using_for_directive.library_name is None:
            self.__library_name = None
        elif isinstance(using_for_directive.library_name, SolcUserDefinedTypeName):
            self.__library_name = UserDefinedTypeName(
                init, using_for_directive.library_name, self
            )
        elif isinstance(using_for_directive.library_name, SolcIdentifierPath):
            self.__library_name = IdentifierPath(
                init, using_for_directive.library_name, self
            )

        if using_for_directive.type_name is None:
            self.__type_name = None
        else:
            self.__type_name = TypeNameAbc.from_ast(
                init, using_for_directive.type_name, self
            )

    @property
    def parent(self) -> Union[ContractDefinition, SourceUnit]:
        return self._parent

    @property
    def functions(self) -> Optional[Tuple[IdentifierPath]]:
        if self.__functions is None:
            return None
        return tuple(self.__functions)

    @property
    def library_name(self) -> Optional[Union[IdentifierPath, UserDefinedTypeName]]:
        return self.__library_name

    @property
    def type_name(self) -> Optional[TypeNameAbc]:
        return self.__type_name
