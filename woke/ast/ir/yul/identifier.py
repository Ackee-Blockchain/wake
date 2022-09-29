from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Union

from ...nodes import YulIdentifier
from ..utils import IrInitTuple
from .abc import YulAbc

if TYPE_CHECKING:
    from ..statement.inline_assembly import ExternalReference
    from .assignment import Assignment
    from .expression_statement import ExpressionStatement
    from .for_loop import ForLoop
    from .function_call import FunctionCall
    from .if_statement import If
    from .switch import Switch
    from .variable_declaration import VariableDeclaration


class Identifier(YulAbc):
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
    _name: str
    _external_reference: Optional[ExternalReference]

    def __init__(self, init: IrInitTuple, identifier: YulIdentifier, parent: YulAbc):
        super().__init__(init, identifier, parent)
        self._name = identifier.name
        self._external_reference = None

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
    def name(self) -> str:
        return self._name

    @property
    def external_reference(self) -> Optional[ExternalReference]:
        return self._external_reference
