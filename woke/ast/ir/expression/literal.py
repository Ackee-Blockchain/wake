from typing import Optional, Set, Tuple

from woke.ast.enums import LiteralKind, ModifiesStateFlag
from woke.ast.ir.abc import IrAbc, SolidityAbc
from woke.ast.ir.expression.abc import ExpressionAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcLiteral


class Literal(ExpressionAbc):
    """
    TBD
    """

    _ast_node: SolcLiteral
    _parent: SolidityAbc  # TODO: make this more specific

    _hex_value: str
    _kind: LiteralKind
    _subdenomination: Optional[str]
    _value: Optional[str]

    def __init__(self, init: IrInitTuple, literal: SolcLiteral, parent: SolidityAbc):
        super().__init__(init, literal, parent)
        self._hex_value = literal.hex_value
        self._kind = literal.kind
        self._subdenomination = literal.subdenomination
        self._value = literal.value

    @property
    def parent(self) -> SolidityAbc:
        return self._parent

    @property
    def hex_value(self) -> str:
        return self._hex_value

    @property
    def kind(self) -> LiteralKind:
        return self._kind

    @property
    def subdenomination(self) -> Optional[str]:
        return self._subdenomination

    @property
    def value(self) -> Optional[str]:
        return self._value

    @property
    def is_ref_to_state_variable(self) -> bool:
        return False

    @property
    def modifies_state(self) -> Set[Tuple[IrAbc, ModifiesStateFlag]]:
        return set()
