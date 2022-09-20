from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Union

from woke.ast.enums import YulLiteralValueKind
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import YulLiteral

from .abc import YulAbc

if TYPE_CHECKING:
    from .assignment import Assignment
    from .case_statement import Case
    from .expression_statement import ExpressionStatement
    from .for_loop import ForLoop
    from .function_call import FunctionCall
    from .if_statement import If
    from .switch import Switch
    from .variable_declaration import VariableDeclaration


class Literal(YulAbc):
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
        Case,
    ]
    _kind: YulLiteralValueKind
    _type: str
    _value: Optional[str]
    _hex_value: Optional[str]

    def __init__(self, init: IrInitTuple, literal: YulLiteral, parent: YulAbc):
        super().__init__(init, literal, parent)
        self._kind = literal.kind
        self._type = literal.type
        self._value = literal.value
        self._hex_value = literal.hex_value

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
        Case,
    ]:
        return self._parent

    @property
    def kind(self) -> YulLiteralValueKind:
        return self._kind

    @property
    def type(self) -> str:
        return self._type

    @property
    def value(self) -> Optional[str]:
        return self._value

    @property
    def hex_value(self) -> Optional[str]:
        return self._hex_value
