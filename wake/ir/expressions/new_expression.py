from __future__ import annotations

from typing import TYPE_CHECKING, Iterator, Set, Tuple, Union

from wake.ir.abc import IrAbc, SolidityAbc
from wake.ir.ast import SolcNewExpression
from wake.ir.enums import ModifiesStateFlag
from wake.ir.expressions.abc import ExpressionAbc
from wake.ir.type_names.abc import TypeNameAbc
from wake.ir.types import Contract
from wake.ir.utils import IrInitTuple

if TYPE_CHECKING:
    from ..statements.abc import StatementAbc
    from ..yul.abc import YulAbc


class NewExpression(ExpressionAbc):
    """
    A new expression may create:

    - a new contract, e.g. `:::solidity new ERC20()`,
    - a new array, e.g. `:::solidity new uint[](10)`,
    - a new `:::solidity bytes` or `:::solidity string`, e.g. `:::solidity new bytes(10)`.
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
        """
        Is:

        - [UserDefinedTypeName][wake.ir.type_names.user_defined_type_name.UserDefinedTypeName] referencing [ContractDefinition][wake.ir.declarations.contract_definition.ContractDefinition] when creating a new contract,
        - [ArrayTypeName][wake.ir.type_names.array_type_name.ArrayTypeName] when creating a new array,
        - [ElementaryTypeName][wake.ir.type_names.elementary_type_name.ElementaryTypeName] when creating new `:::solidity bytes` or `:::solidity string`.

        Returns:
            Type name of the object to be created.
        """
        return self._type_name

    @property
    def is_ref_to_state_variable(self) -> bool:
        return False

    @property
    def modifies_state(
        self,
    ) -> Set[Tuple[Union[ExpressionAbc, StatementAbc, YulAbc], ModifiesStateFlag]]:
        if isinstance(self.type, Contract):
            return {(self, ModifiesStateFlag.DEPLOYS_CONTRACT)}
        else:
            return set()
