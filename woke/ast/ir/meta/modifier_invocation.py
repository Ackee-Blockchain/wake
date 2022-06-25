from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional, Union

from ..expression.abc import ExpressionAbc
from ..expression.identifier import Identifier
from .identifier_path import IdentifierPath

if TYPE_CHECKING:
    from ..declaration.function_definition import FunctionDefinition

from woke.ast.ir.abc import IrAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcIdentifier, SolcIdentifierPath, SolcModifierInvocation


class ModifierInvocation(IrAbc):
    _ast_node: SolcModifierInvocation
    _parent: FunctionDefinition

    __modifier_name: Union[Identifier, IdentifierPath]
    __arguments: Optional[List[ExpressionAbc]]

    def __init__(
        self,
        init: IrInitTuple,
        modifier_invocation: SolcModifierInvocation,
        parent: IrAbc,
    ):
        super().__init__(init, modifier_invocation, parent)
        if isinstance(modifier_invocation.modifier_name, SolcIdentifier):
            self.__modifier_name = Identifier(
                init, modifier_invocation.modifier_name, self
            )
        elif isinstance(modifier_invocation.modifier_name, SolcIdentifierPath):
            self.__modifier_name = IdentifierPath(
                init, modifier_invocation.modifier_name, self
            )

        if modifier_invocation.arguments is None:
            self.__arguments = None
        else:
            self.__arguments = [
                ExpressionAbc.from_ast(init, argument, self)
                for argument in modifier_invocation.arguments
            ]

    @property
    def parent(self) -> FunctionDefinition:
        return self._parent

    @property
    def modifier_name(self) -> Union[Identifier, IdentifierPath]:
        return self.__modifier_name

    @property
    def arguments(self) -> Optional[List[ExpressionAbc]]:
        return self.__arguments
