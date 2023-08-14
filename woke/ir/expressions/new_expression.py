from typing import Iterator, Set, Tuple

from woke.ir.abc import IrAbc, SolidityAbc
from woke.ir.ast import SolcNewExpression
from woke.ir.enums import ModifiesStateFlag
from woke.ir.expressions.abc import ExpressionAbc
from woke.ir.type_names.abc import TypeNameAbc
from woke.ir.types import Contract
from woke.ir.utils import IrInitTuple


class NewExpression(ExpressionAbc):
    """
    TBD
    """

    _ast_node: SolcNewExpression
    _parent: SolidityAbc  # TODO: make this more specific

    _type_name: TypeNameAbc

    def __init__(
        self, init: IrInitTuple, new_expression: SolcNewExpression, parent: SolidityAbc
    ):
        super().__init__(init, new_expression, parent)
        self._type_name = TypeNameAbc.from_ast(init, new_expression.type_name, self)

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        yield from self._type_name

    @property
    def parent(self) -> SolidityAbc:
        return self._parent

    @property
    def type_name(self) -> TypeNameAbc:
        return self._type_name

    @property
    def is_ref_to_state_variable(self) -> bool:
        return False

    @property
    def modifies_state(self) -> Set[Tuple[IrAbc, ModifiesStateFlag]]:
        if isinstance(self.type, Contract):
            return {(self, ModifiesStateFlag.DEPLOYS_CONTRACT)}
        else:
            return set()
