from __future__ import annotations

import weakref
from typing import TYPE_CHECKING, Optional, Union

from wake.ir.ast import SolcYulIdentifier

from ..abc import is_not_none
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
    Represents an identifier referencing a [YulFunctionDefinition][wake.ir.yul.function_definition.YulFunctionDefinition], a [YulVariableDeclaration][wake.ir.yul.variable_declaration.YulVariableDeclaration], or a Solidity [VariableDeclaration][wake.ir.declarations.variable_declaration.VariableDeclaration] through an [ExternalReference][wake.ir.statements.inline_assembly.ExternalReference].
    """

    _parent: weakref.ReferenceType[
        Union[
            YulAssignment,
            YulExpressionStatement,
            YulForLoop,
            YulIf,
            YulSwitch,
            YulVariableDeclaration,
            YulFunctionCall,
        ]
    ]
    _name: str
    _external_reference: Optional[weakref.ReferenceType[ExternalReference]]

    def __init__(
        self, init: IrInitTuple, identifier: SolcYulIdentifier, parent: YulAbc
    ):
        super().__init__(init, identifier, parent)
        self._name = identifier.name
        self._external_reference = None

    @classmethod
    def _strip_weakrefs(cls, state: dict):
        super()._strip_weakrefs(state)
        del state["_external_reference"]

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
        return super().parent

    @property
    def name(self) -> str:
        """
        Returns:
            Name of the identifier.
        """
        return self._name

    @property
    def external_reference(self) -> Optional[ExternalReference]:
        """
        Is not `None` if the identifier is an external reference to a Solidity variable.

        !!! example
            `:::solidity foo` in the following example:

            ```solidity
            uint foo;
            assembly {
                foo := 1
            }
            ```

        Returns:
            Object describing the external reference to a Solidity variable.
        """
        if self._external_reference is None:
            return None
        else:
            return is_not_none(self._external_reference())
