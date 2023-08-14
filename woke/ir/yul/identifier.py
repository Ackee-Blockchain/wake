from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Union

from woke.ir.ast import SolcYulIdentifier

from ..utils import IrInitTuple
from .abc import YulAbc

if TYPE_CHECKING:
    from ..statements.inline_assembly import ExternalReference
    from .assignment import YulAssignment
    from .expression_statement import YulExpressionStatement
    from .for_loop import YulForLoop
    from .function_call import YulFunctionCall
    from .if_statement import YulIf
    from .switch import YulSwitch
    from .variable_declaration import YulVariableDeclaration


class YulIdentifier(YulAbc):
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
    _name: str
    _external_reference: Optional[ExternalReference]

    def __init__(
        self, init: IrInitTuple, identifier: SolcYulIdentifier, parent: YulAbc
    ):
        super().__init__(init, identifier, parent)
        self._name = identifier.name
        self._external_reference = None

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
    def name(self) -> str:
        return self._name

    @property
    def external_reference(self) -> Optional[ExternalReference]:
        return self._external_reference
