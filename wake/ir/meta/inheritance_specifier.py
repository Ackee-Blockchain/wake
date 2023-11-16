from __future__ import annotations

from typing import TYPE_CHECKING, Iterator, List, Optional, Union

from ..expressions.abc import ExpressionAbc
from ..type_names.user_defined_type_name import UserDefinedTypeName
from ..utils import IrInitTuple
from .identifier_path import IdentifierPath

if TYPE_CHECKING:
    from ..declarations.contract_definition import ContractDefinition

from wake.ir.abc import IrAbc, SolidityAbc
from wake.ir.ast import (
    SolcIdentifierPath,
    SolcInheritanceSpecifier,
    SolcUserDefinedTypeName,
)


class InheritanceSpecifier(SolidityAbc):
    """
    !!! example
        `:::solidity A(0x1234567890123456789012345678901234567890)` in the following code:
        ```solidity
        contract A {
            address immutable owner;

            constructor(address _owner) {
                owner = _owner;
            }
        }

        contract B is A(0x1234567890123456789012345678901234567890) {}
        ```
    """

    _ast_node: SolcInheritanceSpecifier
    _parent: ContractDefinition

    _base_name: Union[IdentifierPath, UserDefinedTypeName]
    _arguments: Optional[List[ExpressionAbc]]

    def __init__(
        self,
        init: IrInitTuple,
        inheritance_specifier: SolcInheritanceSpecifier,
        parent: ContractDefinition,
    ):
        super().__init__(init, inheritance_specifier, parent)

        if isinstance(inheritance_specifier.base_name, SolcIdentifierPath):
            self._base_name = IdentifierPath(
                init, inheritance_specifier.base_name, self
            )
        elif isinstance(inheritance_specifier.base_name, SolcUserDefinedTypeName):
            self._base_name = UserDefinedTypeName(
                init, inheritance_specifier.base_name, self
            )

        if inheritance_specifier.arguments is None:
            self._arguments = None
        else:
            self._arguments = []
            for argument in inheritance_specifier.arguments:
                self._arguments.append(ExpressionAbc.from_ast(init, argument, self))

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        yield from self._base_name
        if self._arguments is not None:
            for argument in self._arguments:
                yield from argument

    @property
    def parent(self) -> ContractDefinition:
        """
        Returns:
            Parent IR node.
        """
        return self._parent

    @property
    def base_name(self) -> Union[IdentifierPath, UserDefinedTypeName]:
        """
        The returned IR node holds a reference to the base contract definition ([ContractDefinition][wake.ir.declarations.contract_definition.ContractDefinition]).
        !!! example
            `A` in the following code:
            ```solidity
            contract B is A(0x1234567890123456789012345678901234567890) {}
            ```

        Returns:
            IR node representing the base contract name.
        """
        return self._base_name

    @property
    def arguments(self) -> Optional[List[ExpressionAbc]]:
        """
        !!! warning
            Is `None` when there are no round brackets after the inheritance specifier name.
            ```solidity
            contract B is A {}
            ```

            Is an empty list when there are round brackets but no arguments.
            ```solidity
            contract B is A() {}
            ```
        !!! example
            `:::solidity 0x1234567890123456789012345678901234567890` in the following code:
            ```solidity
            contract B is A(0x1234567890123456789012345678901234567890) {}
            ```

        Returns:
            Arguments of the base constructor call, if provided.
        """
        return self._arguments
