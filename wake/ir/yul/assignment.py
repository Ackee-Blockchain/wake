from __future__ import annotations

from typing import TYPE_CHECKING, Iterator, List, Set, Tuple, Union

from wake.ir.ast import (
    SolcYulAssignment,
    SolcYulFunctionCall,
    SolcYulIdentifier,
    SolcYulLiteral,
)
from wake.ir.utils import IrInitTuple

from ..enums import ModifiesStateFlag
from .abc import YulAbc, YulStatementAbc
from .function_call import YulFunctionCall
from .identifier import YulIdentifier
from .literal import YulLiteral

if TYPE_CHECKING:
    from ..expressions.abc import ExpressionAbc
    from ..statements.abc import StatementAbc
    from .block import YulBlock


class YulAssignment(YulStatementAbc):
    """
    !!! important
        Should not be confused with `:::solidity let a, b := foo()` which is a [YulVariableDeclaration][wake.ir.yul.variable_declaration.YulVariableDeclaration].

    !!! example
        `:::solidity a, b := foo()` in the following example:

        ```solidity
        uint a;
        uint b;
        assembly {
            function foo() -> x, y {
                x := 1
                y := 2
            }
            a, b := foo()
        }
        ```
    """

    _parent: YulBlock
    _value: Union[YulFunctionCall, YulIdentifier, YulLiteral]
    _variable_names: List[YulIdentifier]

    def __init__(
        self, init: IrInitTuple, assignment: SolcYulAssignment, parent: YulAbc
    ):
        super().__init__(init, assignment, parent)
        if isinstance(assignment.value, SolcYulFunctionCall):
            self._value = YulFunctionCall(init, assignment.value, self)
        elif isinstance(assignment.value, SolcYulIdentifier):
            self._value = YulIdentifier(init, assignment.value, self)
        elif isinstance(assignment.value, SolcYulLiteral):
            self._value = YulLiteral(init, assignment.value, self)
        else:
            assert False, f"Unexpected type: {type(assignment.value)}"
        self._variable_names = [
            YulIdentifier(init, variable_name, self)
            for variable_name in assignment.variable_names
        ]

    def __iter__(self) -> Iterator[YulAbc]:
        yield self
        yield from self._value
        for variable_name in self._variable_names:
            yield from variable_name

    @property
    def parent(self) -> YulBlock:
        """
        Returns:
            Parent IR node.
        """
        return self._parent

    @property
    def value(self) -> Union[YulFunctionCall, YulIdentifier, YulLiteral]:
        """
        Returns:
            Value that is assigned to the variables.
        """
        return self._value

    @property
    def variable_names(self) -> Tuple[YulIdentifier, ...]:
        """
        Returns:
            Identifiers of variables that are assigned to in the order they appear in the source code.
        """
        return tuple(self._variable_names)

    @property
    def modifies_state(
        self,
    ) -> Set[Tuple[Union[ExpressionAbc, StatementAbc, YulAbc], ModifiesStateFlag]]:
        return self._value.modifies_state
