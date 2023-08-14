from __future__ import annotations

from typing import TYPE_CHECKING, Union

from woke.ir.abc import SolidityAbc
from woke.ir.ast import SolcStructuredDocumentation
from woke.ir.utils import IrInitTuple

if TYPE_CHECKING:
    from ..declarations.contract_definition import ContractDefinition
    from ..declarations.error_definition import ErrorDefinition
    from ..declarations.event_definition import EventDefinition
    from ..declarations.function_definition import FunctionDefinition
    from ..declarations.modifier_definition import ModifierDefinition
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
        ErrorDefinition,
        EventDefinition,
        FunctionDefinition,
        ModifierDefinition,
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
        ErrorDefinition,
        EventDefinition,
        FunctionDefinition,
        ModifierDefinition,
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
