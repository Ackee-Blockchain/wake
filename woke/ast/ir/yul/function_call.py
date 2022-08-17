from __future__ import annotations

from typing import TYPE_CHECKING, List, Tuple, Union

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
    _parent: Union[
        Assignment,
        ExpressionStatement,
        ForLoop,
        If,
        Switch,
        VariableDeclaration,
        FunctionCall,
    ]
    __arguments: List[Union["FunctionCall", Identifier, Literal]]
    __function_name: Identifier

    def __init__(
        self, init: IrInitTuple, function_call: YulFunctionCall, parent: YulAbc
    ):
        super().__init__(init, function_call, parent)
        self.__function_name = Identifier(init, function_call.function_name, self)
        self.__arguments = []
        for argument in function_call.arguments:
            if isinstance(argument, YulFunctionCall):
                self.__arguments.append(FunctionCall(init, argument, self))
            elif isinstance(argument, YulIdentifier):
                self.__arguments.append(Identifier(init, argument, self))
            elif isinstance(argument, YulLiteral):
                self.__arguments.append(Literal(init, argument, self))
            else:
                assert False, f"Unexpected type: {type(argument)}"

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
        return tuple(self.__arguments)

    @property
    def function_name(self) -> Identifier:
        return self.__function_name
