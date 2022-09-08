from __future__ import annotations

from abc import ABC
from typing import Iterator, Set, Tuple

from woke.ast.nodes import YulNode

from ...enums import ModifiesStateFlag
from ..abc import IrAbc


class YulAbc(IrAbc, ABC):
    """
    Abstract base class for all Yul IR nodes.
    """
    _ast_node: YulNode

    def __iter__(self) -> Iterator[YulAbc]:
        yield self

    @property
    def ast_node(self) -> YulNode:
        return self._ast_node

    @property
    # @abstractmethod
    def modifies_state(self) -> Set[Tuple[IrAbc, ModifiesStateFlag]]:
        return set()  # TODO
