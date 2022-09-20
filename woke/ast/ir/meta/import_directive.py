from __future__ import annotations

import logging
import re
from collections import deque
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path, PurePath
from typing import TYPE_CHECKING, Deque, Iterator, List, Optional, Set, Tuple

from ..expression.identifier import Identifier
from ..reference_resolver import CallbackParams

if TYPE_CHECKING:
    from .source_unit import SourceUnit

from woke.ast.nodes import AstNodeId, SolcImportDirective

from ..abc import IrAbc, SolidityAbc
from ..utils import IrInitTuple

logger = logging.getLogger(__name__)

ENCODING = "utf-8"

FILENAME = r"""(?P<filename>'.*[^\\]'|".*[^\\]")"""
SYMBOL = r"[_a-zA-Z][_a-zA-Z0-9]*"
ALIAS = r"\s*{symbol}(?:\s+as\s+{symbol})?\s*".format(symbol=SYMBOL)
IMPORT_FILENAME_RE = re.compile(
    r"import\s*{filename}\s*".format(filename=FILENAME).encode(ENCODING)
)
IMPORT_AS_FROM_RE = re.compile(
    r"import\s*\*\s*as\s+{symbol}\s+from\s*{filename}\s*".format(
        filename=FILENAME, symbol=SYMBOL
    ).encode(ENCODING)
)
IMPORT_AS_RE = re.compile(
    r"import\s*{filename}\s*as\s+{symbol}\s*".format(
        filename=FILENAME, symbol=SYMBOL
    ).encode(ENCODING)
)
IMPORT_ALIAS_LIST = re.compile(
    r"import\s*{{{alias}(?:,{alias})*}}\s*from\s*{filename}\s*".format(
        alias=ALIAS, filename=FILENAME
    ).encode(ENCODING)
)


@dataclass
class SymbolAlias:
    """
    Helper class representing a symbol alias in an import directive of the`:::solidity import {symbol as alias} from "file.sol";` form.

    !!! example
        `symbol` is the `foreign` attribute and `alias` is the `local` attribute in the following example:
        ```solidity
        import {symbol as alias} from "file.sol";
        ```

    Attributes:
        foreign (Identifier): Identifier referencing the symbol in the imported file.
        local (Optional[str]): Alias name of the imported symbol (if any).
    """

    foreign: Identifier
    local: Optional[str]


class ImportDirective(SolidityAbc):
    """
    !!! example
        ```solidity
        import "SafeLib.sol";
        ```
        ```solidity
        import "SafeLib.sol" as SafeLib;
        ```
        ```solidity
        import * as SafeLib from "SafeLib.sol";
        ```
        ```solidity
        import { SafeType as CustomSafeType } from "SafeLib.sol";
        ```
    """

    _ast_node: SolcImportDirective
    _parent: SourceUnit

    _source_unit_name: PurePath
    _import_string: str
    _imported_file: Path
    _source_unit_id: AstNodeId
    _symbol_aliases: List[SymbolAlias]
    _unit_alias: Optional[str]

    def __init__(
        self,
        init: IrInitTuple,
        import_directive: SolcImportDirective,
        parent: SolidityAbc,
    ):
        super().__init__(init, import_directive, parent)
        self._source_unit_name = PurePath(import_directive.absolute_path)
        self._import_string = import_directive.file
        self._imported_file = init.cu.source_unit_name_to_path(self._source_unit_name)
        self._source_unit_id = import_directive.source_unit
        self._symbol_aliases = []
        if len(import_directive.unit_alias) > 0:
            self._unit_alias = import_directive.unit_alias
        else:
            self._unit_alias = None

        for alias in import_directive.symbol_aliases:
            self._symbol_aliases.append(
                SymbolAlias(Identifier(init, alias.foreign, self), alias.local)
            )
        self._reference_resolver.register_post_process_callback(
            self._post_process, priority=-1
        )

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        for symbol_alias in self._symbol_aliases:
            yield from symbol_alias.foreign

    def _post_process(self, callback_params: CallbackParams):
        # referenced declaration ID is missing (for whatever reason) in import directive symbol aliases
        # for example `import { SafeType } from "SafeLib.sol";`
        # fix: find these reference IDs manually
        for symbol_alias in self._symbol_aliases:
            source_units_queue: Deque[SourceUnit] = deque(
                [callback_params.source_units[self._imported_file]]
            )
            processed_source_units: Set[Path] = {self._imported_file}
            referenced_declaration = None

            while source_units_queue and referenced_declaration is None:
                imported_source_unit = source_units_queue.pop()

                for declaration in imported_source_unit.declarations_iter():
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
        """
        Returns:
            Parent IR node.
        """
        return self._parent

    @property
    def source_unit_name(self) -> PurePath:
        """
        Returns:
            Source unit name of the imported file.
        """
        return self._source_unit_name

    @property
    def imported_file(self) -> Path:
        """
        Returns:
            Absolute path of the imported file.
        """
        return self._imported_file

    @property
    def import_string(self) -> str:
        """
        Returns:
            Import string as it appears in the source code.
        """
        return self._import_string

    @property
    def source_unit(self) -> SourceUnit:
        """
        Returns:
            Source unit imported by this import directive.
        """
        from .source_unit import SourceUnit

        node = self._reference_resolver.resolve_node(
            self._source_unit_id, self._cu_hash
        )
        assert isinstance(node, SourceUnit)
        return node

    @property
    def symbol_aliases(self) -> Tuple[SymbolAlias]:
        """
        Is only set in the case of `:::solidity import { SafeType as CustomSafeType } from "SafeLib.sol";` import directive type.
        Returns:
            Symbol aliases present in the import directive.
        """
        return tuple(self._symbol_aliases)

    @property
    def unit_alias(self) -> Optional[str]:
        """
        !!! example
            Is `SafeLib` in the case of these import directives:
            ```solidity
            import "SafeLib.sol" as SafeLib;
            ```
            ```solidity
            import * as SafeLib from "SafeLib.sol";
            ```

            Is `None` in the case of these import directives:
            ```solidity
            import "SafeLib.sol";
            ```
            ```solidity
            import { SafeType as CustomSafeType } from "SafeLib.sol";
            ```
        Returns:
            Alias for the namespace of the imported source unit.
        """
        return self._unit_alias

    @property
    @lru_cache(maxsize=2048)
    def import_string_pos(self) -> Tuple[int, int]:
        """
        Returns:
            Byte offsets (start, end) of the import string in the source file.
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
