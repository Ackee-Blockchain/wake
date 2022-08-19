from __future__ import annotations

from abc import ABC
from typing import Iterator

from woke.ast.nodes import YulNode

from ...enums import ModifiesStateFlag
from ..abc import IrAbc


class YulAbc(IrAbc, ABC):
    _ast_node: YulNode

    def __iter__(self) -> Iterator[YulAbc]:
        yield self

    @property
    def ast_node(self) -> YulNode:
        return self._ast_node

    @property
    # @abstractmethod
    def modifies_state(self) -> ModifiesStateFlag:
        return ModifiesStateFlag(0)
