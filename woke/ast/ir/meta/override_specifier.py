from __future__ import annotations

from typing import TYPE_CHECKING, Iterator, List, Tuple, Union

from ..type_name.user_defined_type_name import UserDefinedTypeName
from .identifier_path import IdentifierPath

if TYPE_CHECKING:
    from ..declaration.function_definition import FunctionDefinition
    from ..declaration.modifier_definition import ModifierDefinition
    from ..declaration.variable_declaration import VariableDeclaration

from woke.ast.ir.abc import IrAbc, SolidityAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import (
    SolcIdentifierPath,
    SolcOverrideSpecifier,
    SolcUserDefinedTypeName,
)


class OverrideSpecifier(SolidityAbc):
    """
    !!! example
        An override specifier can be used:

        - in a [FunctionDefinition][woke.ast.ir.declaration.function_definition.FunctionDefinition]:
            - `:::solidity override` in line 19,
        - in a [ModifierDefinition][woke.ast.ir.declaration.modifier_definition.ModifierDefinition]:
            - `:::solidity override` in line 12,
        - in a [VariableDeclaration][woke.ast.ir.declaration.variable_declaration.VariableDeclaration]:
            - `:::solidity override(IERC20)` in line 17.

        ```solidity linenums="1"
        interface IERC20 {
            function transfer(address to, uint256 value) external returns (bool);

            function allowance(address owner, address spender) external view returns (uint256);
        }

        abstract contract ERC20 is IERC20 {
            modifier EOA() virtual;
        }

        contract C is ERC20 {
            modifier EOA() override {
                require(msg.sender == tx.origin);
                _;
            }

            mapping(address => mapping(address => uint256)) public override(IERC20) allowance;

            function transfer(address to, uint256 value) external override returns (bool) {
                // ...
            }
        }
        ```
    """
    _ast_node: SolcOverrideSpecifier
    _parent: Union[FunctionDefinition, ModifierDefinition, VariableDeclaration]

    _overrides: List[Union[IdentifierPath, UserDefinedTypeName]]

    def __init__(
        self,
        init: IrInitTuple,
        override_specifier: SolcOverrideSpecifier,
        parent: SolidityAbc,
    ):
        super().__init__(init, override_specifier, parent)
        self._overrides = []

        for override in override_specifier.overrides:
            if isinstance(override, SolcIdentifierPath):
                self._overrides.append(IdentifierPath(init, override, self))
            elif isinstance(override, SolcUserDefinedTypeName):
                self._overrides.append(UserDefinedTypeName(init, override, self))

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        for override in self._overrides:
            yield from override

    @property
    def parent(
        self,
    ) -> Union[FunctionDefinition, ModifierDefinition, VariableDeclaration]:
        """
        Returns:
            Parent IR node.
        """
        return self._parent

    @property
    def overrides(self) -> Tuple[Union[IdentifierPath, UserDefinedTypeName]]:
        """
        !!! note
            Is empty when there are no curly braces after the `:::solidity override` keyword.
        Returns:
            Tuple of IR nodes referencing the contract or interface whose declaration is being overridden.
        """
        return tuple(self._overrides)
