import logging
from pathlib import Path
from typing import List, Optional, Tuple

from woke.compile.compilation_unit import CompilationUnit

from ..nodes import SolcImportDirective, SolcPragmaDirective, SolcSourceUnit
from .import_directive import ImportDirective
from .pragma_directive import PragmaDirective

logger = logging.getLogger(__name__)


class SourceUnit:
    __license: Optional[str]
    __source_unit_name: str
    __path: Path
    __pragmas: List[PragmaDirective]
    __imports: List[ImportDirective]

    def __init__(
        self,
        path: Path,
        source_unit: SolcSourceUnit,
        source: bytes,
        cu: CompilationUnit,
    ):
        self.__license = source_unit.license
        self.__source_unit_name = source_unit.absolute_path
        self.__path = path.resolve()

        self.__pragmas = []
        self.__imports = []
        for node in source_unit.nodes:
            if isinstance(node, SolcPragmaDirective):
                self.__pragmas.append(PragmaDirective(node, source, cu))
            elif isinstance(node, SolcImportDirective):
                self.__imports.append(ImportDirective(node, source, cu))

    @property
    def license(self) -> Optional[str]:
        """
        The license string of the file (if present).
        """
        return self.__license

    @property
    def source_unit_name(self) -> str:
        """
        The source unit name of the file.
        """
        return self.__source_unit_name

    @property
    def resolved_path(self) -> Path:
        """
        The system path of the file.
        """
        return self.__path

    @property
    def pragmas(self) -> Tuple[PragmaDirective]:
        """
        A tuple of pragma directives present in the file.
        """
        return tuple(self.__pragmas)

    @property
    def imports(self) -> Tuple[ImportDirective]:
        """
        A tuple of import directives present in the file.
        """
        return tuple(self.__imports)
