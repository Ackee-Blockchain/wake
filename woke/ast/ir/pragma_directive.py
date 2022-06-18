import logging
from typing import List, Tuple

from woke.compile.compilation_unit import CompilationUnit

from ..nodes import SolcPragmaDirective
from .abc import IrAbc

logger = logging.getLogger(__name__)


class PragmaDirective(IrAbc):
    _ast_node: SolcPragmaDirective

    __literals: List[str]

    def __init__(self, pragma: SolcPragmaDirective, source: bytes, cu: CompilationUnit):
        super().__init__(pragma, source, cu)
        self.__literals = list(pragma.literals)

    @property
    def literals(self) -> Tuple[str]:
        """
        The literals of the pragma directive.
        """
        return tuple(self.__literals)
