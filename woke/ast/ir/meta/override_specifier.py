from __future__ import annotations

from typing import TYPE_CHECKING, List, Tuple, Union

from ..type_name.user_defined_type_name import UserDefinedTypeName
from .identifier_path import IdentifierPath

if TYPE_CHECKING:
    from ..declaration.function_definition import FunctionDefinition
    from ..declaration.modifier_definition import ModifierDefinition
    from ..declaration.variable_declaration import VariableDeclaration

from woke.ast.ir.abc import IrAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import (
    SolcIdentifierPath,
    SolcOverrideSpecifier,
    SolcUserDefinedTypeName,
)


class OverrideSpecifier(IrAbc):
    _ast_node: SolcOverrideSpecifier
    _parent: Union[FunctionDefinition, ModifierDefinition, VariableDeclaration]

    __overrides: List[Union[IdentifierPath, UserDefinedTypeName]]

    def __init__(
        self,
        init: IrInitTuple,
        override_specifier: SolcOverrideSpecifier,
        parent: IrAbc,
    ):
        super().__init__(init, override_specifier, parent)
        self.__overrides = []

        for override in override_specifier.overrides:
            if isinstance(override, SolcIdentifierPath):
                self.__overrides.append(IdentifierPath(init, override, self))
            elif isinstance(override, SolcUserDefinedTypeName):
                self.__overrides.append(UserDefinedTypeName(init, override, self))

    @property
    def parent(
        self,
    ) -> Union[FunctionDefinition, ModifierDefinition, VariableDeclaration]:
        return self._parent

    @property
    def overrides(self) -> Tuple[Union[IdentifierPath, UserDefinedTypeName]]:
        return tuple(self.__overrides)
