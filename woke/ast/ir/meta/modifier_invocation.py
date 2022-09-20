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
    """
    !!! warning
        Also represents a base constructor invocation.
    !!! example
        - `:::solidity IERC20("MyToken", "MTK")` ([ModifierInvocationKind.BASE_CONSTRUCTOR_SPECIFIER][woke.ast.enums.ModifierInvocationKind.BASE_CONSTRUCTOR_SPECIFIER]),
        - `:::solidity initializer` ([ModifierInvocationKind.MODIFIER_INVOCATION][woke.ast.enums.ModifierInvocationKind.MODIFIER_INVOCATION])

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
        from ..declaration.contract_definition import ContractDefinition
        from ..declaration.modifier_definition import ModifierDefinition

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
        The returned IR node holds a reference to the [ModifierDefinition][woke.ast.ir.declaration.modifier_definition.ModifierDefinition] declaration of the modifier being invoked in the case of the [ModifierInvocationKind.MODIFIER_INVOCATION][woke.ast.enums.ModifierInvocationKind.MODIFIER_INVOCATION] kind.
        In the case of the [ModifierInvocationKind.BASE_CONSTRUCTOR_SPECIFIER][woke.ast.enums.ModifierInvocationKind.BASE_CONSTRUCTOR_SPECIFIER] kind, the returned IR node holds a reference to the [ContractDefinition][woke.ast.ir.declaration.contract_definition.ContractDefinition] whose constructor is being invoked.
        !!! example
            `ERC20` and `initializer` in the following code:
            ```solidity
            constructor() ERC20("MyToken", "MTK") initializer {
                // ...
            }
            ```
        Returns:
            IR node representing the name of the modifier.
        """
        return self._modifier_name

    @property
    def arguments(self) -> Optional[List[ExpressionAbc]]:
        """
        !!! warning
            Is `None` when there are no curly braces after the modifier name.
            ```solidity
            constructor() initializer {}
            ```

            Is an empty list when there are curly braces but no arguments.
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
        return self._arguments
