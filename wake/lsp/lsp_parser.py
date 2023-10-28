from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    DefaultDict,
    Dict,
    List,
    NamedTuple,
    Optional,
    Set,
    Tuple,
    Union,
)

from tree_sitter import Parser
from tree_sitter_solidity import get_parser

from .common_structures import (
    CreateFilesParams,
    DeleteFilesParams,
    MessageType,
    RenameFilesParams,
)
from .document_sync import (
    DidChangeTextDocumentParams,
    DidCloseTextDocumentParams,
    DidOpenTextDocumentParams,
)
from .utils import uri_to_path

if TYPE_CHECKING:
    from .server import LspServer


ENCODING = "utf-16-le"


def _binary_search(lines: List[Tuple[bytes, int]], x: int) -> int:
    l = 0
    r = len(lines)

    while l < r:
        mid = l + (r - l) // 2
        if lines[mid][1] < x + 1:
            l = mid + 1
        else:
            r = mid

    return l - 1


class VersionedFile(NamedTuple):
    text: bytearray
    version: int


class LspParser:
    _parser: Parser
    _files: Dict[Path, VersionedFile]
    _trees: Dict[Path, Any]
    _tree_changed: DefaultDict[Path, bool]
    _line_indexes: Dict[Path, List[Tuple[bytes, int]]]
    _line_endings: Dict[Path, Optional[str]]
    _server: LspServer

    def __init__(self, server: LspServer):
        self._server = server
        self._files = {}
        self._trees = {}
        self._tree_changed = defaultdict(bool)
        self._line_indexes = {}
        self._line_endings = {}
        self._parser = get_parser()

    def __getitem__(self, item: Path) -> Any:
        if item not in self._trees:
            self._trees[item] = self._parser.parse(
                bytes(self._files[item].text),
                encoding="utf16",  # pyright: ignore reportGeneralTypeIssues
            )

        if self._tree_changed[item]:
            self._trees[item] = self._parser.parse(
                self._files[item].text,
                self._trees[item],
                encoding="utf16",  # pyright: ignore reportGeneralTypeIssues
            )
            self._tree_changed[item] = False

        return self._trees[item]

    @property
    def files(self) -> Set[Path]:
        return set(self._files.keys())

    def _setup_line_index(self, file: Path, content: str):
        # UTF-16 encoded lines with prefix length
        encoded_lines: List[Tuple[bytes, int]] = []
        prefix_sum = 0
        line_endings = Counter()
        for line in content.splitlines(keepends=True):
            encoded_line = line.encode(ENCODING)
            encoded_lines.append((encoded_line, prefix_sum))
            prefix_sum += len(encoded_line)

            if line.endswith("\r\n"):
                line_endings["\r\n"] += 1
            elif line.endswith("\n"):
                line_endings["\n"] += 1
            elif line.endswith("\r"):
                line_endings["\r"] += 1

        self._line_indexes[file] = encoded_lines
        try:
            self._line_endings[file] = line_endings.most_common(1)[0][0]
        except IndexError:
            self._line_endings[file] = None

    def _get_byte_offset_from_line_pos(self, file: Path, line: int, col: int) -> int:
        lines = self._line_indexes[file]
        if len(lines) == line:
            if line == 0:
                return col * 2
            return lines[line - 1][1] + len(lines[line - 1][0]) + col * 2

        line_bytes, prefix = lines[line]
        return prefix + col * 2

    def _get_line_pos_from_byte_offset(
        self, file: Path, offset: int
    ) -> Tuple[int, int]:
        encoded_lines = self._line_indexes[file]
        if len(encoded_lines) == 0:
            return 0, offset // 2

        line_num = _binary_search(self._line_indexes[file], offset)
        line_data, prefix_sum = encoded_lines[line_num]
        col_num = (offset - prefix_sum) // 2
        return line_num, col_num

    async def add_change(
        self,
        change: Union[
            DidOpenTextDocumentParams,
            DidChangeTextDocumentParams,
            DidCloseTextDocumentParams,
            CreateFilesParams,
            RenameFilesParams,
            DeleteFilesParams,
        ],
    ) -> None:
        if isinstance(change, DidOpenTextDocumentParams):
            path = uri_to_path(change.text_document.uri).resolve()
            self._files[path] = VersionedFile(
                bytearray(change.text_document.text.encode(ENCODING)),
                change.text_document.version,
            )
            self._setup_line_index(path, change.text_document.text)
        elif isinstance(change, DidChangeTextDocumentParams):
            path = uri_to_path(change.text_document.uri).resolve()
            for content_change in change.content_changes:
                encoded_change = content_change.text.encode(ENCODING)
                start_offset = self._get_byte_offset_from_line_pos(
                    path,
                    content_change.range.start.line,
                    content_change.range.start.character,
                )
                end_offset = self._get_byte_offset_from_line_pos(
                    path,
                    content_change.range.end.line,
                    content_change.range.end.character,
                )

                self._files[path].text[start_offset:end_offset] = bytearray(
                    encoded_change
                )
                self._setup_line_index(
                    path, self._files[path].text.decode(ENCODING)
                )  # TODO: Optimize

                if path in self._trees:
                    new_end_point = self._get_line_pos_from_byte_offset(
                        path, start_offset + len(encoded_change)
                    )
                    self._trees[path].edit(
                        start_byte=start_offset,
                        old_end_byte=end_offset,
                        new_end_byte=start_offset + len(encoded_change),
                        start_point=(
                            content_change.range.start.line,
                            content_change.range.start.character * 2,
                        ),
                        old_end_point=(
                            content_change.range.end.line,
                            content_change.range.end.character * 2,
                        ),
                        new_end_point=(new_end_point[0], new_end_point[1] * 2),
                    )

            self._files[path] = VersionedFile(
                self._files[path].text, change.text_document.version
            )
            self._tree_changed[path] = True
        elif isinstance(change, RenameFilesParams):
            for rename in change.files:
                old_file = uri_to_path(rename.old_uri)
                new_file = uri_to_path(rename.new_uri)

                if old_file in self._files:
                    self._files[new_file] = self._files.pop(old_file)
                if old_file in self._trees:
                    self._trees[new_file] = self._trees.pop(old_file)
                if old_file in self._tree_changed:
                    self._tree_changed[new_file] = self._tree_changed.pop(old_file)
                if old_file in self._line_indexes:
                    self._line_indexes[new_file] = self._line_indexes.pop(old_file)
        elif isinstance(change, DeleteFilesParams):
            for delete in change.files:
                path = uri_to_path(delete.uri)
                if path in self._files:
                    del self._files[path]
                if path in self._trees:
                    del self._trees[path]
                if path in self._tree_changed:
                    del self._tree_changed[path]
                if path in self._line_indexes:
                    del self._line_indexes[path]

    async def get_node_at_position(self, file: Path, line: int, col: int):
        """
        Returns the most nested node at the given position.
        """
        offset = self._get_byte_offset_from_line_pos(file, line, col)
        cursor = self[file].walk()
        last_node = cursor.node

        while True:
            while cursor.goto_first_child():
                if cursor.node.start_byte <= offset < cursor.node.end_byte:
                    pass
                else:
                    while cursor.goto_next_sibling():
                        if cursor.node.start_byte <= offset < cursor.node.end_byte:
                            break

            if cursor.node.start_byte <= offset < cursor.node.end_byte:
                pass
            else:
                cursor.goto_parent()

            if cursor.node == last_node:
                break
            last_node = cursor.node

        return last_node

    def get_line_ending(self, file: Path) -> Optional[str]:
        try:
            return self._line_endings[file]
        except KeyError:
            return None
