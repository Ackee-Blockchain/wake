from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List, Tuple

if TYPE_CHECKING:
    from wake.ir.meta.source_unit import SourceUnit

from wake.core import get_logger
from wake.ir.ast import SolcPragmaDirective

from ..abc import SolidityAbc
from ..utils import IrInitTuple

logger = get_logger(__name__)


class PragmaDirective(SolidityAbc):
    _ast_node: SolcPragmaDirective
    _parent: SourceUnit

    _literals: List[str]

    def __init__(
        self, init: IrInitTuple, pragma: SolcPragmaDirective, parent: SolidityAbc
    ):
        super().__init__(init, pragma, parent)
        self._literals = list(pragma.literals)

    @property
    def parent(self) -> SourceUnit:
        """
        Returns:
            Parent IR node.
        """
        return self._parent

    @property
    def literals(self) -> Tuple[str, ...]:
        """
        !!! example
            `:::py ('solidity', '^', '0.8', '||', '0.7', '.1', '-', '0.7', '.6')` for the following pragma:
            ```solidity
            pragma solidity ^0.8 || 0.7.1 - 0.7.6;
            ```
        !!! example
            `:::py ('abicoder', 'v2')` for the following pragma:
            ```solidity
            pragma abicoder v2;
            ```
        !!! example
            `:::py ('experimental', 'SMTChecker')` for the following pragma:
            ```solidity
            pragma experimental SMTChecker;
            ```

        Returns:
            Literals of the pragma directive.
        """
        return tuple(self._literals)
