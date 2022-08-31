from __future__ import annotations

from typing import TYPE_CHECKING, Iterator, List, Optional, Union

from ..expression.abc import ExpressionAbc
from ..expression.identifier import Identifier
from .identifier_path import IdentifierPath
from ..reference_resolver import CallbackParams
from ...enums import ModifierInvocationKind

if TYPE_CHECKING:
    from ..declaration.function_definition import FunctionDefinition

from woke.ast.ir.abc import IrAbc, SolidityAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcIdentifier, SolcIdentifierPath, SolcModifierInvocation


class ModifierInvocation(SolidityAbc):
    _ast_node: SolcModifierInvocation
    _parent: FunctionDefinition

    __kind: Optional[ModifierInvocationKind]
    __modifier_name: Union[Identifier, IdentifierPath]
    __arguments: Optional[List[ExpressionAbc]]

    def __init__(
        self,
        init: IrInitTuple,
        modifier_invocation: SolcModifierInvocation,
        parent: SolidityAbc,
    ):
        super().__init__(init, modifier_invocation, parent)
        self.__kind = None
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

        self._reference_resolver.register_post_process_callback(self.__post_process)

    def __post_process(self, callback_params: CallbackParams):
        from ..declaration.contract_definition import ContractDefinition
        from ..declaration.modifier_definition import ModifierDefinition

        referenced_declaration = self.modifier_name.referenced_declaration
        if isinstance(referenced_declaration, ModifierDefinition):
            self.__kind = ModifierInvocationKind.MODIFIER_INVOCATION
        elif isinstance(referenced_declaration, ContractDefinition):
            self.__kind = ModifierInvocationKind.BASE_CONSTRUCTOR_SPECIFIER
        else:
            assert False, f"Unexpected declaration type: {referenced_declaration}"

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        yield from self.__modifier_name
        if self.__arguments is not None:
            for argument in self.__arguments:
                yield from argument

    @property
    def parent(self) -> FunctionDefinition:
        return self._parent

    @property
    def kind(self) -> ModifierInvocationKind:
        assert self.__kind is not None
        return self.__kind

    @property
    def modifier_name(self) -> Union[Identifier, IdentifierPath]:
        return self.__modifier_name

    @property
    def arguments(self) -> Optional[List[ExpressionAbc]]:
        return self.__arguments
