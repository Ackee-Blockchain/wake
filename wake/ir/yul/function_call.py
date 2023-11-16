from __future__ import annotations

from typing import TYPE_CHECKING, Iterator, List, Tuple, Union

from wake.ir.ast import SolcYulFunctionCall, SolcYulIdentifier, SolcYulLiteral
from wake.ir.utils import IrInitTuple

from .abc import YulAbc
from .identifier import YulIdentifier
from .literal import YulLiteral

if TYPE_CHECKING:
    from .assignment import YulAssignment
    from .expression_statement import YulExpressionStatement
    from .for_loop import YulForLoop
    from .if_statement import YulIf
    from .switch import YulSwitch
    from .variable_declaration import YulVariableDeclaration


class YulFunctionCall(YulAbc):
    """
    Represents a call to a "builtin" function/instruction (see [Solidity docs](https://docs.soliditylang.org/en/latest/yul.html#evm-dialect)) or a user-defined [YulFunctionDefinition][wake.ir.yul.function_definition.YulFunctionDefinition].

    !!! example
        `foo` and `stop()` in the following example:

        ```solidity
        assembly {
            function foo() -> x, y {
                x := 1
                y := 2
            }
            foo()
            stop()
        }
        ```
    """

    _parent: Union[
        YulAssignment,
        YulExpressionStatement,
        YulForLoop,
        YulIf,
        YulSwitch,
        YulVariableDeclaration,
        YulFunctionCall,
    ]
    _arguments: List[Union["YulFunctionCall", YulIdentifier, YulLiteral]]
    _function_name: YulIdentifier

    def __init__(
        self, init: IrInitTuple, function_call: SolcYulFunctionCall, parent: YulAbc
    ):
        super().__init__(init, function_call, parent)
        self._function_name = YulIdentifier(init, function_call.function_name, self)
        self._arguments = []
        for argument in function_call.arguments:
            if isinstance(argument, SolcYulFunctionCall):
                self._arguments.append(YulFunctionCall(init, argument, self))
            elif isinstance(argument, SolcYulIdentifier):
                self._arguments.append(YulIdentifier(init, argument, self))
            elif isinstance(argument, SolcYulLiteral):
                self._arguments.append(YulLiteral(init, argument, self))
            else:
                assert False, f"Unexpected type: {type(argument)}"

    def __iter__(self) -> Iterator[YulAbc]:
        yield self
        yield from self._function_name
        for argument in self._arguments:
            yield from argument

    @property
    def parent(
        self,
    ) -> Union[
        YulAssignment,
        YulExpressionStatement,
        YulForLoop,
        YulIf,
        YulSwitch,
        YulVariableDeclaration,
        YulFunctionCall,
    ]:
        """
        Returns:
            Parent IR node.
        """
        return self._parent

    @property
    def arguments(
        self,
    ) -> Tuple[Union[YulFunctionCall, YulIdentifier, YulLiteral], ...]:
        """
        Returns:
            Arguments of the function call in the order they appear in the source code.
        """
        return tuple(self._arguments)

    @property
    def function_name(self) -> YulIdentifier:
        """
        Returns:
            Name of the function that is called.
        """
        return self._function_name
