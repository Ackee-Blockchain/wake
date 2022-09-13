from __future__ import annotations

from typing import TYPE_CHECKING

from .abc import YulAbc

if TYPE_CHECKING:
    from .block import Block


class Break(YulAbc):
    """
    TBD
    """
    _parent: Block

    @property
    def parent(self) -> Block:
        return self._parent
