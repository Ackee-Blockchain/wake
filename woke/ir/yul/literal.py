from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Union

from woke.ir.ast import SolcYulLiteral
from woke.ir.enums import YulLiteralValueKind
from woke.ir.utils import IrInitTuple

from .abc import YulAbc

if TYPE_CHECKING:
    from .assignment import YulAssignment
    from .case_statement import YulCase
    from .expression_statement import YulExpressionStatement
    from .for_loop import YulForLoop
    from .function_call import YulFunctionCall
    from .if_statement import YulIf
    from .switch import YulSwitch
    from .variable_declaration import YulVariableDeclaration


class YulLiteral(YulAbc):
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
        YulCase,
    ]
    _kind: YulLiteralValueKind
    _type: str
    _value: Optional[str]
    _hex_value: Optional[str]

    def __init__(self, init: IrInitTuple, literal: SolcYulLiteral, parent: YulAbc):
        super().__init__(init, literal, parent)
        self._kind = literal.kind
        self._type = literal.type
        self._value = literal.value
        self._hex_value = literal.hex_value

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
        YulCase,
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
