from __future__ import annotations

from abc import ABC

from woke.ast.nodes import YulNode

from ..abc import IrAbc


class YulAbc(IrAbc, ABC):
    _ast_node: YulNode

    @property
    def ast_node(self) -> YulNode:
        return self._ast_node
