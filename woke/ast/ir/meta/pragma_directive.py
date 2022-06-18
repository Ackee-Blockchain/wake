from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List, Tuple

if TYPE_CHECKING:
    from woke.ast.ir.meta.source_unit import SourceUnit

from woke.ast.nodes import SolcPragmaDirective

from ..abc import IrAbc
from ..utils import IrInitTuple

logger = logging.getLogger(__name__)


class PragmaDirective(IrAbc):
    _ast_node: SolcPragmaDirective
    _parent: SourceUnit

    __literals: List[str]

    def __init__(self, init: IrInitTuple, pragma: SolcPragmaDirective, parent: IrAbc):
        super().__init__(init, pragma, parent)
        self.__literals = list(pragma.literals)

    @property
    def parent(self) -> SourceUnit:
        return self._parent

    @property
    def literals(self) -> Tuple[str]:
        """
        The literals of the pragma directive.
        """
        return tuple(self.__literals)
