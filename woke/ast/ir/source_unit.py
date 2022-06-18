import logging
from typing import List, Optional, Tuple

from ..nodes import (
    SolcEnumDefinition,
    SolcImportDirective,
    SolcPragmaDirective,
    SolcSourceUnit,
)
from .abc import IrAbc
from .enum_definition import EnumDefinition
from .import_directive import ImportDirective
from .pragma_directive import PragmaDirective
from .utils import IrInitTuple

logger = logging.getLogger(__name__)


class SourceUnit(IrAbc):
    _ast_node: SolcSourceUnit

    __license: Optional[str]
    __source_unit_name: str
    __pragmas: List[PragmaDirective]
    __imports: List[ImportDirective]
    __enums: List[EnumDefinition]

    def __init__(
        self,
        init: IrInitTuple,
        source_unit: SolcSourceUnit,
    ):
        super().__init__(init, source_unit, None)
        self.__license = source_unit.license
        self.__source_unit_name = source_unit.absolute_path

        self.__pragmas = []
        self.__imports = []
        self.__enums = []
        for node in source_unit.nodes:
            if isinstance(node, SolcPragmaDirective):
                self.__pragmas.append(PragmaDirective(init, node, self))
            elif isinstance(node, SolcImportDirective):
                self.__imports.append(ImportDirective(init, node, self))
            elif isinstance(node, SolcEnumDefinition):
                self.__enums.append(EnumDefinition(init, node, self))

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

    @property
    def enums(self) -> Tuple[EnumDefinition]:
        """
        A tuple of enum definitions present in the file.
        """
        return tuple(self.__enums)
