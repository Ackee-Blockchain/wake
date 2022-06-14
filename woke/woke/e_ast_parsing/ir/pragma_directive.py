import logging
from typing import List, Tuple

from woke.d_compile.compilation_unit import CompilationUnit
from woke.e_ast_parsing.b_solc.c_ast_nodes import SolcPragmaDirective


logger = logging.getLogger(__name__)


class PragmaDirective:
    __literals: List[str]

    def __init__(self, pragma: SolcPragmaDirective, source: bytes, cu: CompilationUnit):
        self.__literals = list(pragma.literals)

    @property
    def literals(self) -> Tuple[str]:
        """
        The literals of the pragma directive.
        """
        return tuple(self.__literals)
