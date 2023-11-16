from __future__ import annotations

from typing import TYPE_CHECKING, Union

from wake.ir.abc import SolidityAbc
from wake.ir.ast import SolcStructuredDocumentation
from wake.ir.utils import IrInitTuple

if TYPE_CHECKING:
    from ..declarations.contract_definition import ContractDefinition
    from ..declarations.enum_definition import EnumDefinition
    from ..declarations.error_definition import ErrorDefinition
    from ..declarations.event_definition import EventDefinition
    from ..declarations.function_definition import FunctionDefinition
    from ..declarations.modifier_definition import ModifierDefinition
    from ..declarations.struct_definition import StructDefinition
    from ..declarations.variable_declaration import VariableDeclaration


class StructuredDocumentation(SolidityAbc):
    """
    !!! example
        Lines 1-4 in the following example:
        ```solidity linenums="1"
        /// @title A simulator for trees
        /// @author John
        /// @notice You can use this contract for only the most basic simulation
        /// @dev All function calls are currently implemented without side effects
        contract Tree {
            function multiply(uint a) public pure returns(uint) {
                return a * 7;
            }
        }
        ```
    """

    _ast_node: SolcStructuredDocumentation
    _parent: Union[
        ContractDefinition,
        EnumDefinition,
        ErrorDefinition,
        EventDefinition,
        FunctionDefinition,
        ModifierDefinition,
        StructDefinition,
        VariableDeclaration,
    ]

    _text: str

    def __init__(
        self,
        init: IrInitTuple,
        structured_documentation: SolcStructuredDocumentation,
        parent: SolidityAbc,
    ):
        super().__init__(init, structured_documentation, parent)
        self._text = structured_documentation.text

    @property
    def parent(
        self,
    ) -> Union[
        ContractDefinition,
        EnumDefinition,
        ErrorDefinition,
        EventDefinition,
        FunctionDefinition,
        ModifierDefinition,
        StructDefinition,
        VariableDeclaration,
    ]:
        """
        Returns:
            Parent IR node.
        """
        return self._parent

    @property
    def text(self) -> str:
        """
        Does not include the leading `///` or `/**` and trailing `*/`.

        Returns:
            [NatSpec](https://docs.soliditylang.org/en/latest/natspec-format.html) documentation string.
        """
        return self._text
