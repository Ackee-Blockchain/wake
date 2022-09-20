from __future__ import annotations

from typing import TYPE_CHECKING, Iterator, List, Tuple, Union

from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import YulFunctionCall, YulIdentifier, YulLiteral

from .abc import YulAbc
from .identifier import Identifier
from .literal import Literal

if TYPE_CHECKING:
    from .assignment import Assignment
    from .expression_statement import ExpressionStatement
    from .for_loop import ForLoop
    from .if_statement import If
    from .switch import Switch
    from .variable_declaration import VariableDeclaration


class FunctionCall(YulAbc):
    """
    TBD
    """
    _parent: Union[
        Assignment,
        ExpressionStatement,
        ForLoop,
        If,
        Switch,
        VariableDeclaration,
        FunctionCall,
    ]
    _arguments: List[Union["FunctionCall", Identifier, Literal]]
    _function_name: Identifier

    def __init__(
        self, init: IrInitTuple, function_call: YulFunctionCall, parent: YulAbc
    ):
        super().__init__(init, function_call, parent)
        self._function_name = Identifier(init, function_call.function_name, self)
        self._arguments = []
        for argument in function_call.arguments:
            if isinstance(argument, YulFunctionCall):
                self._arguments.append(FunctionCall(init, argument, self))
            elif isinstance(argument, YulIdentifier):
                self._arguments.append(Identifier(init, argument, self))
            elif isinstance(argument, YulLiteral):
                self._arguments.append(Literal(init, argument, self))
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
        Assignment,
        ExpressionStatement,
        ForLoop,
        If,
        Switch,
        VariableDeclaration,
        FunctionCall,
    ]:
        return self._parent

    @property
    def arguments(self) -> Tuple[Union["FunctionCall", Identifier, Literal]]:
        return tuple(self._arguments)

    @property
    def function_name(self) -> Identifier:
        return self._function_name
