from __future__ import annotations

import logging
import re
from collections import deque
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path, PurePath
from typing import TYPE_CHECKING, Deque, List, Optional, Set, Tuple

from ..expression.identifier import Identifier
from ..reference_resolver import CallbackParams

if TYPE_CHECKING:
    from .source_unit import SourceUnit

from woke.ast.nodes import AstNodeId, SolcImportDirective

from ..abc import IrAbc
from ..utils import IrInitTuple

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


@dataclass
class SymbolAlias:
    foreign: Identifier
    local: Optional[str]


class ImportDirective(IrAbc):
    _ast_node: SolcImportDirective
    _parent: SourceUnit

    __source_unit_name: PurePath
    __import_string: str
    __imported_file: Path
    __symbol_aliases: List[SymbolAlias]

    def __init__(
        self, init: IrInitTuple, import_directive: SolcImportDirective, parent: IrAbc
    ):
        super().__init__(init, import_directive, parent)
        self.__source_unit_name = PurePath(import_directive.absolute_path)
        self.__import_string = import_directive.file
        self.__imported_file = init.cu.source_unit_name_to_path(self.__source_unit_name)
        self.__symbol_aliases = []

        for alias in import_directive.symbol_aliases:
            self.__symbol_aliases.append(
                SymbolAlias(Identifier(init, alias.foreign, self), alias.local)
            )
        self._reference_resolver.register_post_process_callback(
            self.__post_process, priority=-1
        )

    def __post_process(self, callback_params: CallbackParams):
        # referenced declaration ID is missing (for whatever reason) in import directive symbol aliases
        # for example `import { SafeType } from "SafeLib.sol";`
        # fix: find these reference IDs manually
        for symbol_alias in self.__symbol_aliases:
            source_units_queue: Deque[SourceUnit] = deque(
                [callback_params.source_units[self.__imported_file]]
            )
            processed_source_units: Set[Path] = {self.__imported_file}
            referenced_declaration = None

            while source_units_queue and referenced_declaration is None:
                imported_source_unit = source_units_queue.pop()

                for declaration in imported_source_unit.declarations:
                    if declaration.canonical_name == symbol_alias.foreign.name:
                        referenced_declaration = declaration
                        break

                for import_ in imported_source_unit.imports:
                    if import_.imported_file not in processed_source_units:
                        source_units_queue.append(
                            callback_params.source_units[import_.imported_file]
                        )
                        processed_source_units.add(import_.imported_file)

            assert referenced_declaration is not None
            node_path_order = self._reference_resolver.get_node_path_order(
                AstNodeId(referenced_declaration.ast_node_id),
                referenced_declaration.cu_hash,
            )
            referenced_declaration_id = (
                self._reference_resolver.get_ast_id_from_cu_node_path_order(
                    node_path_order, self.cu_hash
                )
            )
            symbol_alias.foreign._referenced_declaration_id = referenced_declaration_id

    @property
    def parent(self) -> SourceUnit:
        return self._parent

    @property
    def source_unit_name(self) -> PurePath:
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
    def symbol_aliases(self) -> Tuple[SymbolAlias]:
        """
        The symbols that are specified (and optionally aliased) in the import directive.
        """
        return tuple(self.__symbol_aliases)

    @property
    @lru_cache(maxsize=None)
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
        return source_start + match.start("filename"), source_start + match.end(
            "filename"
        )
