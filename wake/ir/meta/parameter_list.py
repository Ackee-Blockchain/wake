from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Iterator, List, Tuple, Union

if TYPE_CHECKING:
    from ..declarations.error_definition import ErrorDefinition
    from ..declarations.event_definition import EventDefinition
    from ..declarations.function_definition import FunctionDefinition
    from ..declarations.modifier_definition import ModifierDefinition
    from ..type_names.function_type_name import FunctionTypeName
    from .try_catch_clause import TryCatchClause

from wake.core import get_logger
from wake.ir.abc import IrAbc, SolidityAbc
from wake.ir.ast import SolcParameterList
from wake.ir.utils import IrInitTuple

from ..declarations.variable_declaration import VariableDeclaration

logger = get_logger(__name__)


class ParameterList(SolidityAbc):
    """
    !!! example
        A parameter list can be used:

        - in an [ErrorDefinition][wake.ir.declarations.error_definition.ErrorDefinition]:
            - `:::solidity (uint requested, uint available)` on line 2,
        - in an [EventDefinition][wake.ir.declarations.event_definition.EventDefinition]:
            - `:::solidity (address indexed previousOwner, address indexed newOwner)` on line 3,
        - in a [FunctionDefinition][wake.ir.declarations.function_definition.FunctionDefinition]:
            - `:::solidity (uint a, uint b)` on line 12 as function parameters,
            - `:::solidity (uint256)` on line 12 as function return parameters,
        - in a [FunctionTypeName][wake.ir.type_names.function_type_name.FunctionTypeName]:
            - `:::solidity (string memory, uint)` on line 5 as function type name parameters,
            - `:::solidity (bool)` on line 5 as function type name return parameters,
        - in a [ModifierDefinition][wake.ir.declarations.modifier_definition.ModifierDefinition]:
            - `:::solidity (uint x)` on line 7,
        - in a [TryCatchClause][wake.ir.meta.try_catch_clause.TryCatchClause]:
            - `:::solidity (bool success)` on line 17 as try clause parameters,
            - `:::solidity (string memory reason)` on line 19 as catch clause parameters.

        ```solidity linenums="1"
        contract C {
            error InsufficientBalance(uint requested, uint available);
            event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);

            function (string memory, uint) external returns (bool) externalFunction;

            modifier onlyPositive(uint x) {
                require(x > 0, "x must be positive");
                _;
            }

            function add(uint a, uint b) onlyPositive(a) public pure returns (uint256) {
                return a + b;
            }

            function callExternalFunction() public {
                try externalFunction("abc", 123) returns (bool success) {
                    // ...
                } catch Error(string memory reason) {
                    // ...
                }
            }
        }
        ```
    """

    _ast_node: SolcParameterList
    _parent: Union[
        ErrorDefinition,
        EventDefinition,
        FunctionDefinition,
        FunctionTypeName,
        ModifierDefinition,
        TryCatchClause,
    ]

    _parameters: List[VariableDeclaration]

    def __init__(
        self, init: IrInitTuple, parameter_list: SolcParameterList, parent: SolidityAbc
    ):
        super().__init__(init, parameter_list, parent)

        self._parameters = []
        for parameter in parameter_list.parameters:
            self._parameters.append(VariableDeclaration(init, parameter, self))

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        for parameter in self._parameters:
            yield from parameter

    @property
    def parent(
        self,
    ) -> Union[
        ErrorDefinition,
        EventDefinition,
        FunctionDefinition,
        FunctionTypeName,
        ModifierDefinition,
        TryCatchClause,
    ]:
        """
        Returns:
            Parent IR node.
        """
        return self._parent

    @property
    def parameters(self) -> Tuple[VariableDeclaration, ...]:
        """
        Can be empty.

        Returns:
            Variable declarations of the parameter list.
        """
        return tuple(self._parameters)
