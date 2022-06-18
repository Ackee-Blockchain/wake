import logging
import re
from pathlib import Path
from typing import Tuple

from woke.compile.compilation_unit import CompilationUnit

from ..nodes import SolcImportDirective
from .abc import IrAbc

logger = logging.getLogger(__name__)

ENCODING = "utf-8"

FILENAME = r"""(?P<filename>'.*[^\\]'|".*[^\\]")"""
SYMBOL = r"[_a-zA-Z][_a-zA-Z0-9]*"
ALIAS = r"\s*{symbol}(?:\s+as\s+{symbol})?\s*".format(symbol=SYMBOL)
IMPORT_FILENAME_RE = re.compile(
    r"import\s+{filename}\s*".format(filename=FILENAME).encode(ENCODING)
)
IMPORT_AS_FROM_RE = re.compile(
    r"import\s+\*\s*as\s+{symbol}\s+from\s*{filename}\s*".format(
        filename=FILENAME, symbol=SYMBOL
    ).encode(ENCODING)
)
IMPORT_AS_RE = re.compile(
    r"import\s+{filename}\s*as\s+{symbol}\s*".format(
        filename=FILENAME, symbol=SYMBOL
    ).encode(ENCODING)
)
IMPORT_ALIAS_LIST = re.compile(
    r"import\s+{{{alias}(?:,{alias})*}}\s*from\s*{filename}\s*".format(
        alias=ALIAS, filename=FILENAME
    ).encode(ENCODING)
)


class ImportDirective(IrAbc):
    _ast_node: SolcImportDirective

    __source_unit_name: str
    __import_string: str
    __imported_file: Path
    __import_string_pos: Tuple[int, int]

    def __init__(
        self, import_directive: SolcImportDirective, source: bytes, cu: CompilationUnit
    ):
        super().__init__(import_directive, source, cu)
        self.__source_unit_name = import_directive.absolute_path
        self.__import_string = import_directive.file
        self.__imported_file = cu.source_unit_name_to_path(self.__source_unit_name)

        source_start = import_directive.src.byte_offset
        source_end = source_start + import_directive.src.byte_length
        directive_source = source[source_start:source_end]

        res = (
            IMPORT_FILENAME_RE,
            IMPORT_AS_FROM_RE,
            IMPORT_AS_RE,
            IMPORT_ALIAS_LIST,
        )
        matches = list(re.match(directive_source) for re in res)
        assert any(matches)
        match = next(m for m in matches if m)
        self.__import_string_pos = source_start + match.start("filename"), match.end(
            "filename"
        ) - match.start("filename")

    @property
    def source_unit_name(self) -> str:
        """
        The source unit name of the file that is imported.
        """
        return self.__source_unit_name

    @property
    def imported_file(self) -> Path:
        """
        The path of the file that is imported.
        """
        return self.__imported_file

    @property
    def import_string(self) -> str:
        """
        The import string as it appears in the source code.
        """
        return self.__import_string

    @property
    def import_string_pos(self) -> Tuple[int, int]:
        """
        The byte position and the byte length of the import string in the source file.
        """
        return self.__import_string_pos
