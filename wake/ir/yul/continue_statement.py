from __future__ import annotations

from typing import TYPE_CHECKING

from .abc import YulStatementAbc

if TYPE_CHECKING:
    from .block import YulBlock


class YulContinue(YulStatementAbc):
    """
    TBD
    """

    _parent: YulBlock

    @property
    def parent(self) -> YulBlock:
        return self._parent
