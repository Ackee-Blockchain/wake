from __future__ import annotations

from typing import TYPE_CHECKING

from .abc import YulStatementAbc

if TYPE_CHECKING:
    from .block import Block


class Leave(YulStatementAbc):
    """
    TBD
    """
    _parent: Block

    @property
    def parent(self) -> Block:
        return self._parent
