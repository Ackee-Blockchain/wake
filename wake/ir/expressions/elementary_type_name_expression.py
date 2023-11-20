from typing import Iterator, Set, Tuple

from wake.ir.ast import SolcElementaryTypeNameExpression
from wake.ir.enums import ModifiesStateFlag
from wake.ir.utils import IrInitTuple

from ..abc import IrAbc, SolidityAbc
from ..type_names.elementary_type_name import ElementaryTypeName
from .abc import ExpressionAbc


class ElementaryTypeNameExpression(ExpressionAbc):
    """
    May be used:

    - in a [FunctionCall][wake.ir.expressions.function_call.FunctionCall] type conversion expressions, e.g. `:::solidity address(this)`,
    - as `type` argument, e.g. `:::solidity type(uint256).max`,
    - as a [FunctionCall][wake.ir.expressions.function_call.FunctionCall] argument, e.g. `:::solidity abi.decode(x, (uint256))`.
    """

    _ast_node: SolcElementaryTypeNameExpression
    _parent: SolidityAbc  # TODO: make this more specific

    _type_name: ElementaryTypeName

    def __init__(
        self,
        init: IrInitTuple,
        elementary_type_name_expression: SolcElementaryTypeNameExpression,
        parent: SolidityAbc,
    ):
        super().__init__(init, elementary_type_name_expression, parent)
        self._type_name = ElementaryTypeName(
            init, elementary_type_name_expression.type_name, self
        )

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        yield from self._type_name

    @property
    def parent(self) -> SolidityAbc:
        return self._parent

    @property
    def type_name(self) -> ElementaryTypeName:
        """
        Returns:
            Type name referenced by the expression.
        """
        return self._type_name

    @property
    def is_ref_to_state_variable(self) -> bool:
        return False

    @property
    def modifies_state(self) -> Set[Tuple[IrAbc, ModifiesStateFlag]]:
        return set()
