from __future__ import annotations

from typing import TYPE_CHECKING, Iterator, List, Optional, Set, Tuple, Union

from wake.ir.ast import (
    SolcYulFunctionCall,
    SolcYulIdentifier,
    SolcYulLiteral,
    SolcYulVariableDeclaration,
)

from ..enums import ModifiesStateFlag
from ..utils import IrInitTuple
from .abc import YulAbc, YulStatementAbc
from .function_call import YulFunctionCall
from .identifier import YulIdentifier
from .literal import YulLiteral
from .typed_name import YulTypedName

if TYPE_CHECKING:
    from ..expressions.abc import ExpressionAbc
    from ..statements.abc import StatementAbc
    from .block import YulBlock


class YulVariableDeclaration(YulStatementAbc):
    """
    Represents a new variable declaration with the following structure:

    ```solidity
    let <variables> := <value>
    ```

    !!! example
        `:::solidity let a, b := foo()` in the following example:

        ```solidity
        assembly {
            function foo() -> x, y {
                x := 1
                y := 2
            }

            let a, b := foo()
        }
        ```
    """

    _parent: YulBlock
    _variables: List[YulTypedName]
    _value: Optional[Union[YulFunctionCall, YulIdentifier, YulLiteral]]

    def __init__(
        self,
        init: IrInitTuple,
        variable_declaration: SolcYulVariableDeclaration,
        parent: YulAbc,
    ):
        super().__init__(init, variable_declaration, parent)
        self._variables = [
            YulTypedName(init, variable, self)
            for variable in variable_declaration.variables
        ]
        if variable_declaration.value is None:
            self._value = None
        elif isinstance(variable_declaration.value, SolcYulFunctionCall):
            self._value = YulFunctionCall(init, variable_declaration.value, self)
        elif isinstance(variable_declaration.value, SolcYulIdentifier):
            self._value = YulIdentifier(init, variable_declaration.value, self)
        elif isinstance(variable_declaration.value, SolcYulLiteral):
            self._value = YulLiteral(init, variable_declaration.value, self)
        else:
            assert False, f"Unexpected type: {type(variable_declaration.value)}"

    def __iter__(self) -> Iterator[YulAbc]:
        yield self
        for variable in self._variables:
            yield from variable
        if self._value is not None:
            yield from self._value

    @property
    def parent(self) -> YulBlock:
        """
        Returns:
            Parent IR node.
        """
        return self._parent

    @property
    def variables(self) -> Tuple[YulTypedName, ...]:
        """
        Returns:
            Tuple of variables declared in this statement.
        """
        return tuple(self._variables)

    @property
    def value(self) -> Optional[Union[YulFunctionCall, YulIdentifier, YulLiteral]]:
        """
        Returns:
            Value assigned to the variables.
        """
        return self._value

    @property
    def modifies_state(
        self,
    ) -> Set[Tuple[Union[ExpressionAbc, StatementAbc, YulAbc], ModifiesStateFlag]]:
        if self._value is None:
            return set()
        return self._value.modifies_state
