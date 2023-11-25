from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Iterator, Set, Tuple, Union

from wake.ir.ast import YulNode
from wake.ir.enums import ModifiesStateFlag
from wake.ir.utils import IrInitTuple

from ..abc import IrAbc

if TYPE_CHECKING:
    from ..expressions.abc import ExpressionAbc
    from ..statements.abc import StatementAbc
    from ..statements.inline_assembly import InlineAssembly


class YulAbc(IrAbc, ABC):
    """
    Abstract base class for all Yul IR nodes.
    """

    _ast_node: YulNode
    _inline_assembly: InlineAssembly

    def __init__(self, init: IrInitTuple, yul: YulNode, parent: IrAbc):
        super().__init__(init, yul, parent)
        assert init.inline_assembly is not None
        self._inline_assembly = init.inline_assembly

    def __iter__(self) -> Iterator[YulAbc]:
        yield self

    @property
    def ast_node(self) -> YulNode:
        return self._ast_node

    @property
    @abstractmethod
    def modifies_state(
        self,
    ) -> Set[Tuple[Union[ExpressionAbc, StatementAbc, YulAbc], ModifiesStateFlag]]:
        """
        WARNING:
            Is not considered stable and so is not exported in the documentation.

        Returns:
            Set of child IR nodes (including `self`) that modify the blockchain state and flags describing how the state is modified.
        """
        ...

    @property
    def inline_assembly(self) -> InlineAssembly:
        """
        Returns:
            Inline assembly statement that contains this Yul node.
        """
        return self._inline_assembly


class YulStatementAbc(YulAbc, ABC):
    """
    Abstract base class for all Yul IR statements.
    """
