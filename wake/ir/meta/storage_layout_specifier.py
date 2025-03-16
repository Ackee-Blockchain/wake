from __future__ import annotations

import weakref
from typing import TYPE_CHECKING, Iterator

from wake.ir.utils import IrInitTuple

if TYPE_CHECKING:
    from wake.ir.declarations.contract_definition import ContractDefinition

from wake.ir.abc import IrAbc, SolidityAbc
from wake.ir.ast import SolcStorageLayoutSpecifier
from wake.ir.expressions.abc import ExpressionAbc


class StorageLayoutSpecifier(SolidityAbc):
    """
    !!! example
        `layout at (10 + 20)` in the following code:
        ```solidity
        contract C layout at (10 + 20) {}
        ```
    """

    _ast_node: SolcStorageLayoutSpecifier
    _parent: weakref.ReferenceType[ContractDefinition]

    _base_slot_expression: ExpressionAbc

    def __init__(
        self,
        init: IrInitTuple,
        storage_layout_specifier: SolcStorageLayoutSpecifier,
        parent: ContractDefinition,
    ):
        super().__init__(init, storage_layout_specifier, parent)

        self._base_slot_expression = ExpressionAbc.from_ast(
            init, storage_layout_specifier.base_slot_expression, self
        )

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        yield self._base_slot_expression

    @property
    def parent(self) -> ContractDefinition:
        """
        Returns:
            Parent IR node.
        """
        return super().parent

    @property
    def children(self) -> Iterator[ExpressionAbc]:
        """
        Yields:
            Direct children of this node.
        """
        yield self._base_slot_expression

    @property
    def base_slot_expression(self) -> ExpressionAbc:
        """
        Returns:
            Expression representing the starting slot of the storage layout.
        """
        return self._base_slot_expression
