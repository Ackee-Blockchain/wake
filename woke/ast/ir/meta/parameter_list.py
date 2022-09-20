from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Iterator, List, Tuple, Union

if TYPE_CHECKING:
    from ..declaration.error_definition import ErrorDefinition
    from ..declaration.event_definition import EventDefinition
    from ..declaration.function_definition import FunctionDefinition
    from ..declaration.modifier_definition import ModifierDefinition
    from ..type_name.function_type_name import FunctionTypeName
    from .try_catch_clause import TryCatchClause

from woke.ast.ir.abc import IrAbc, SolidityAbc
from woke.ast.ir.declaration.variable_declaration import VariableDeclaration
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcParameterList

logger = logging.getLogger(__name__)


class ParameterList(SolidityAbc):
    """
    !!! example
        A parameter list can be used:

        - in an [ErrorDefinition][woke.ast.ir.declaration.error_definition.ErrorDefinition]:
            - `:::solidity (uint requested, uint available)` in line 2,
        - in an [EventDefinition][woke.ast.ir.declaration.event_definition.EventDefinition]:
            - `:::solidity (address indexed previousOwner, address indexed newOwner)` in line 3,
        - in a [FunctionDefinition][woke.ast.ir.declaration.function_definition.FunctionDefinition]:
            - `:::solidity (uint a, uint b)` in line 12 as function parameters,
            - `:::solidity (uint256)` in line 12 as function return parameters,
        - in a [FunctionTypeName][woke.ast.ir.type_name.function_type_name.FunctionTypeName]:
            - `:::solidity (string memory, uint)` in line 5 as function type name parameters,
            - `:::solidity (bool)` in line 5 as function type name return parameters,
        - in a [ModifierDefinition][woke.ast.ir.declaration.modifier_definition.ModifierDefinition]:
            - `:::solidity (uint x)` in line 7,
        - in a [TryCatchClause][woke.ast.ir.meta.try_catch_clause.TryCatchClause]:
            - `:::solidity (bool success)` in line 17 as try clause parameters,
            - `:::solidity (string memory reason)` in line 19 as catch clause parameters.

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
    def parameters(self) -> Tuple[VariableDeclaration]:
        """
        Can be empty.
        Returns:
            Variable declarations of the parameter list.
        """
        return tuple(self._parameters)
