from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Set, Tuple, Union

from wake.ir.ast import SolcYulLiteral
from wake.ir.enums import ModifiesStateFlag, YulLiteralKind
from wake.ir.utils import IrInitTuple

from .abc import YulAbc

if TYPE_CHECKING:
    from ..expressions.abc import ExpressionAbc
    from ..statements.abc import StatementAbc
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
    String literals may have up to 32 characters.

    !!! example
        `:::solidity 10`, `:::solidity 0x1234`, `:::solidity true` and `:::solidity "abcdef"` in the following example are all literals:

        ```solidity
        assembly {
            let x := 10
            x := 0x1234
            x := true
            x := "abcdef"
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
        YulCase,
    ]
    _kind: YulLiteralKind
    _type: str
    _value: str
    _hex_value: Optional[bytes]

    def __init__(self, init: IrInitTuple, literal: SolcYulLiteral, parent: YulAbc):
        super().__init__(init, literal, parent)
        self._kind = literal.kind
        self._type = literal.type
        assert (
            literal.type == ""
        ), f"Expected YulLiteral type to be empty, got {literal.type}"
        assert literal.value is not None, "Expected YulLiteral value to be not None"
        self._value = literal.value
        self._hex_value = (
            bytes.fromhex(literal.hex_value) if literal.hex_value is not None else None
        )

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
        """
        Returns:
            Parent IR node.
        """
        return self._parent

    @property
    def kind(self) -> YulLiteralKind:
        """
        Returns:
            Kind of the literal.
        """
        return self._kind

    # type seems to be always empty
    # @property
    # def type(self) -> str:
    # return self._type

    @property
    def value(self) -> str:
        """
        Returns:
            Value of the literal as it appears in the Yul source code.
        """
        return self._value

    @property
    def hex_value(self) -> Optional[bytes]:
        """
        !!! note
            Only set for [YulLiteralKind.STRING][wake.ir.enums.YulLiteralKind.STRING] literals in Solidity >= 0.8.5.

        Returns:
            Byte representation of the literal.
        """
        return self._hex_value

    @property
    def modifies_state(
        self,
    ) -> Set[Tuple[Union[ExpressionAbc, StatementAbc, YulAbc], ModifiesStateFlag]]:
        return set()
