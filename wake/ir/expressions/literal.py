from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Set, Tuple, Union

from wake.ir.abc import SolidityAbc
from wake.ir.ast import SolcLiteral
from wake.ir.enums import LiteralKind, ModifiesStateFlag
from wake.ir.expressions.abc import ExpressionAbc
from wake.ir.utils import IrInitTuple

if TYPE_CHECKING:
    from ..statements.abc import StatementAbc
    from ..yul.abc import YulAbc


class Literal(ExpressionAbc):
    """
    May represent a literal of the following types (see [LiteralKind][wake.ir.enums.LiteralKind]):

    - boolean, e.g. `true`, `false`,
    - integer, e.g. `-1`, `.2`, `3e10`, `123_456`, `0x123`, `1_002e34`,
    - string, e.g. `"Hello World!"`,
    - hex string, e.g. `hex"1234aabb"`,
    - unicode string, e.g. `unicode"Hello World! 😃"`,
    """

    _ast_node: SolcLiteral
    _parent: SolidityAbc  # TODO: make this more specific

    _hex_value: bytes
    _kind: LiteralKind
    _subdenomination: Optional[str]
    _value: Optional[str]

    def __init__(self, init: IrInitTuple, literal: SolcLiteral, parent: SolidityAbc):
        super().__init__(init, literal, parent)
        self._hex_value = bytes.fromhex(literal.hex_value)
        self._kind = literal.kind
        self._subdenomination = literal.subdenomination
        self._value = literal.value

        # fix prior to 0.7.0 hex string literals had kind `string` instead of `hexString`
        if self._value is None:
            self._kind = LiteralKind.HEX_STRING

    @property
    def parent(self) -> SolidityAbc:
        return self._parent

    @property
    def hex_value(self) -> bytes:
        """
        !!! important
            Does not return the hexadecimal representation, but rather the [value][wake.ir.expressions.literal.Literal.value] encoded into bytes.
            For example, `hex"1234aabb"` would return `b'\x124\xaa\xbb'` and `.2` would return `b'.2'`.

        Returns:
            Hex string literal value.
        """
        return self._hex_value

    @property
    def kind(self) -> LiteralKind:
        """
        Returns:
            Literal kind.
        """
        return self._kind

    @property
    def subdenomination(self) -> Optional[str]:
        """
        !!! example
            For example `wei`, `ether`, `seconds`, `days`, etc.

        Returns:
            Literal subdenomination, if any.
        """
        return self._subdenomination

    @property
    def value(self) -> Optional[str]:
        """
        Is `None` for hex string literals.

        Returns:
            Literal value.
        """
        return self._value

    @property
    def is_ref_to_state_variable(self) -> bool:
        return False

    @property
    def modifies_state(
        self,
    ) -> Set[Tuple[Union[ExpressionAbc, StatementAbc, YulAbc], ModifiesStateFlag]]:
        return set()
