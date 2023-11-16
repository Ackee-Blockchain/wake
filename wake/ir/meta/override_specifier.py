from __future__ import annotations

from typing import TYPE_CHECKING, Iterator, List, Tuple, Union

from ..type_names.user_defined_type_name import UserDefinedTypeName
from .identifier_path import IdentifierPath

if TYPE_CHECKING:
    from ..declarations.function_definition import FunctionDefinition
    from ..declarations.modifier_definition import ModifierDefinition
    from ..declarations.variable_declaration import VariableDeclaration

from wake.ir.abc import IrAbc, SolidityAbc
from wake.ir.ast import (
    SolcIdentifierPath,
    SolcOverrideSpecifier,
    SolcUserDefinedTypeName,
)
from wake.ir.utils import IrInitTuple


class OverrideSpecifier(SolidityAbc):
    """
    !!! example
        An override specifier can be used:

        - in a [FunctionDefinition][wake.ir.declarations.function_definition.FunctionDefinition]:
            - `:::solidity override` on line 19,
        - in a [ModifierDefinition][wake.ir.declarations.modifier_definition.ModifierDefinition]:
            - `:::solidity override` on line 12,
        - in a [VariableDeclaration][wake.ir.declarations.variable_declaration.VariableDeclaration]:
            - `:::solidity override(IERC20)` on line 17.

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
    def overrides(self) -> Tuple[Union[IdentifierPath, UserDefinedTypeName], ...]:
        """
        !!! note
            Is empty when there are no round brackets after the `:::solidity override` keyword.

        Returns:
            Tuple of IR nodes referencing the contract or interface whose declaration is being overridden.
        """
        return tuple(self._overrides)
