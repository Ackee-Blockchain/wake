from __future__ import annotations

from typing import TYPE_CHECKING, Iterator, List, Optional, Tuple, Union

from wake.ir.enums import ModifierInvocationKind

from ..expressions.abc import ExpressionAbc
from ..expressions.identifier import Identifier
from ..reference_resolver import CallbackParams
from .identifier_path import IdentifierPath

if TYPE_CHECKING:
    from ..declarations.function_definition import FunctionDefinition

from wake.ir.abc import IrAbc, SolidityAbc
from wake.ir.ast import SolcIdentifier, SolcIdentifierPath, SolcModifierInvocation
from wake.ir.utils import IrInitTuple


class ModifierInvocation(SolidityAbc):
    """
    !!! warning
        Also represents a base constructor invocation.
    !!! example
        - `:::solidity ERC20("MyToken", "MTK")` ([ModifierInvocationKind.BASE_CONSTRUCTOR_SPECIFIER][wake.ir.enums.ModifierInvocationKind.BASE_CONSTRUCTOR_SPECIFIER]),
        - `:::solidity initializer` ([ModifierInvocationKind.MODIFIER_INVOCATION][wake.ir.enums.ModifierInvocationKind.MODIFIER_INVOCATION])

        in the following code:
        ```solidity
        import Initializable from "@openzeppelin/contracts/proxy/utils/Initializable.sol";

        contract MyContract is ERC20, Initializable {
            constructor() ERC20("MyToken", "MTK") initializer {
                // ...
            }
        }
        ```
    """

    _ast_node: SolcModifierInvocation
    _parent: FunctionDefinition

    _kind: Optional[ModifierInvocationKind]
    _modifier_name: Union[Identifier, IdentifierPath]
    _arguments: Optional[List[ExpressionAbc]]

    def __init__(
        self,
        init: IrInitTuple,
        modifier_invocation: SolcModifierInvocation,
        parent: SolidityAbc,
    ):
        super().__init__(init, modifier_invocation, parent)
        self._kind = None
        if isinstance(modifier_invocation.modifier_name, SolcIdentifier):
            self._modifier_name = Identifier(
                init, modifier_invocation.modifier_name, self
            )
        elif isinstance(modifier_invocation.modifier_name, SolcIdentifierPath):
            self._modifier_name = IdentifierPath(
                init, modifier_invocation.modifier_name, self
            )

        if modifier_invocation.arguments is None:
            self._arguments = None
        else:
            self._arguments = [
                ExpressionAbc.from_ast(init, argument, self)
                for argument in modifier_invocation.arguments
            ]

        self._reference_resolver.register_post_process_callback(self._post_process)

    def _post_process(self, callback_params: CallbackParams):
        from ..declarations.contract_definition import ContractDefinition
        from ..declarations.modifier_definition import ModifierDefinition

        referenced_declaration = self.modifier_name.referenced_declaration
        if isinstance(referenced_declaration, ModifierDefinition):
            self._kind = ModifierInvocationKind.MODIFIER_INVOCATION
        elif isinstance(referenced_declaration, ContractDefinition):
            self._kind = ModifierInvocationKind.BASE_CONSTRUCTOR_SPECIFIER
        else:
            assert False, f"Unexpected declaration type: {referenced_declaration}"

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        yield from self._modifier_name
        if self._arguments is not None:
            for argument in self._arguments:
                yield from argument

    @property
    def parent(self) -> FunctionDefinition:
        """
        Returns:
            Parent IR node.
        """
        return self._parent

    @property
    def kind(self) -> ModifierInvocationKind:
        """
        Returns:
            Kind of the modifier invocation.
        """
        assert self._kind is not None
        return self._kind

    @property
    def modifier_name(self) -> Union[Identifier, IdentifierPath]:
        """
        The returned IR node holds a reference to the [ModifierDefinition][wake.ir.declarations.modifier_definition.ModifierDefinition] declaration of the modifier being invoked in the case of the [ModifierInvocationKind.MODIFIER_INVOCATION][wake.ir.enums.ModifierInvocationKind.MODIFIER_INVOCATION] kind.
        In the case of the [ModifierInvocationKind.BASE_CONSTRUCTOR_SPECIFIER][wake.ir.enums.ModifierInvocationKind.BASE_CONSTRUCTOR_SPECIFIER] kind, the returned IR node holds a reference to the [ContractDefinition][wake.ir.declarations.contract_definition.ContractDefinition] whose constructor is being invoked.
        !!! example
            `ERC20` and `initializer` in the following code:
            ```solidity
            constructor() ERC20("MyToken", "MTK") initializer {
                // ...
            }
            ```

        Until Solidity 0.8.0, modifiers were referenced in [ModifierInvocations][wake.ir.meta.modifier_invocation.ModifierInvocation]
        using [Identifiers][wake.ir.expressions.identifier.Identifier]. Version 0.8.0 started using [IdentifierPaths][wake.ir.meta.identifier_path.IdentifierPath] instead.

        Returns:
            IR node representing the name of the modifier.
        """
        return self._modifier_name

    @property
    def arguments(self) -> Optional[Tuple[ExpressionAbc, ...]]:
        """
        !!! warning
            Is `None` when there are no round brackets after the modifier name.
            ```solidity
            constructor() initializer {}
            ```

            Is an empty list when there are round brackets but no arguments.
            ```solidity
            constructor() initializer() {}
            ```
        !!! example
            `:::solidity "MyToken"` and `:::solidity "MTK"` in the following code:
            ```solidity
            constructor() ERC20("MyToken", "MTK") initializer {
                // ...
            }
            ```

        Returns:
            Arguments of the base constructor or modifier invocation (if any).
        """
        if self._arguments is None:
            return None
        return tuple(self._arguments)
