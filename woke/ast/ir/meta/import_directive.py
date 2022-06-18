from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Tuple

if TYPE_CHECKING:
    from .source_unit import SourceUnit

from woke.ast.nodes import SolcImportDirective

from ..abc import IrAbc
from ..utils import IrInitTuple, lazy_property

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
    _parent: SourceUnit

    __source_unit_name: str
    __import_string: str
    __imported_file: Path

    def __init__(
        self, init: IrInitTuple, import_directive: SolcImportDirective, parent: IrAbc
    ):
        super().__init__(init, import_directive, parent)
        self.__source_unit_name = import_directive.absolute_path
        self.__import_string = import_directive.file
        self.__imported_file = init.cu.source_unit_name_to_path(self.__source_unit_name)

    @property
    def parent(self) -> SourceUnit:
        return self._parent

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

    @lazy_property
    def import_string_pos(self) -> Tuple[int, int]:
        """
        The byte position and the byte length of the import string in the source file.
        """
        source_start = self._ast_node.src.byte_offset

        res = (
            IMPORT_FILENAME_RE,
            IMPORT_AS_FROM_RE,
            IMPORT_AS_RE,
            IMPORT_ALIAS_LIST,
        )
        matches = list(re.match(self._source) for re in res)
        assert any(matches)
        match = next(m for m in matches if m)
        return source_start + match.start("filename"), match.end(
            "filename"
        ) - match.start("filename")
