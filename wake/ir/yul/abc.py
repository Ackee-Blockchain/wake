from __future__ import annotations

from abc import ABC
from typing import TYPE_CHECKING, Iterator, Set, Tuple

from wake.ir.ast import YulNode
from wake.ir.enums import ModifiesStateFlag
from wake.ir.utils import IrInitTuple

from ..abc import IrAbc

if TYPE_CHECKING:
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
    # @abstractmethod
    def modifies_state(self) -> Set[Tuple[IrAbc, ModifiesStateFlag]]:
        return set()  # TODO

    @property
    def inline_assembly(self) -> InlineAssembly:
        return self._inline_assembly


class YulStatementAbc(YulAbc, ABC):
    """
    Abstract base class for all Yul IR statements.
    """

    pass
