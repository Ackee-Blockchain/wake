from __future__ import annotations

from typing import TYPE_CHECKING, Iterator, List, Tuple, Union

from woke.ir.ast import SolcYulFunctionCall, SolcYulIdentifier, SolcYulLiteral
from woke.ir.utils import IrInitTuple

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
    TBD
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
        return self._parent

    @property
    def arguments(
        self,
    ) -> Tuple[Union["YulFunctionCall", YulIdentifier, YulLiteral], ...]:
        return tuple(self._arguments)

    @property
    def function_name(self) -> YulIdentifier:
        return self._function_name
