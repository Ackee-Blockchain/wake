import asyncio
import logging
import platform
import queue
import re
import sys
import threading
from pathlib import Path
from threading import Thread
from typing import Collection, Dict, List, Mapping, Set, Tuple, Union

from intervaltree import IntervalTree

from woke.ast.ir.meta.source_unit import SourceUnit
from woke.ast.ir.reference_resolver import ReferenceResolver
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import AstSolc
from woke.compile import SolcOutput, SolcOutputSelectionEnum
from woke.compile.compilation_unit import CompilationUnit
from woke.compile.compiler import SolidityCompiler
from woke.compile.solc_frontend import SolcOutputError, SolcOutputErrorSeverityEnum
from woke.config import WokeConfig
from woke.lsp.document_sync import (
    DidChangeTextDocumentParams,
    DidCloseTextDocumentParams,
    DidOpenTextDocumentParams,
)
from woke.lsp.utils.uri import uri_to_path

if platform.system() != "Windows":
    from woke.lsp.utils.threaded_child_watcher import ThreadedChildWatcher

logger = logging.getLogger(__name__)


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


class LspCompiler:
    __config: WokeConfig
    __thread: Thread
    __file_changes_queue: queue.Queue

    __processed_files: Set[Path]

    # accessed from the compilation thread
    # full path -> contents
    __files: Dict[Path, str]
    __opened_files: Set[Path]
    __modified_files: Set[Path]
    __compiler: SolidityCompiler
    __output_contents: Dict[Path, str]
    __errors: Set[SolcOutputError]
    __asts: Dict[Path, AstSolc]
    __interval_trees: Dict[Path, IntervalTree]
    __source_units: Dict[Path, SourceUnit]
    __line_indexes: Dict[Path, List[Tuple[bytes, int]]]

    __ir_reference_resolver: ReferenceResolver

    output_ready: threading.Event

    def __init__(self, config: WokeConfig):
        self.__config = config
        self.__file_changes_queue = queue.Queue()
        self.__processed_files = set()
        self.__files = dict()
        self.__opened_files = set()
        self.__modified_files = set()
        self.__compiler = SolidityCompiler(config)
        self.__asts = {}
        self.__interval_trees = {}
        self.__errors = set()
        self.__source_units = {}
        self.__line_indexes = {}
        self.__output_contents = dict()

        self.__ir_reference_resolver = ReferenceResolver()

        self.output_ready = threading.Event()

    def run(self):
        self.__thread = Thread(target=self.__compilation_loop, args=())
        self.__thread.start()

    @property
    def asts(self) -> Dict[Path, AstSolc]:
        return self.__asts

    @property
    def interval_trees(self) -> Dict[Path, IntervalTree]:
        return self.__interval_trees

    @property
    def errors(self) -> Set[SolcOutputError]:
        return self.__errors

    @property
    def source_units(self) -> Dict[Path, SourceUnit]:
        return self.__source_units

    def add_change(
        self,
        change: Union[
            DidOpenTextDocumentParams,
            DidChangeTextDocumentParams,
            DidCloseTextDocumentParams,
        ],
    ) -> None:
        file = uri_to_path(change.text_document.uri)
        if (
            isinstance(change, DidChangeTextDocumentParams)
            or file not in self.__processed_files
        ):
            self.output_ready.clear()
        self.__file_changes_queue.put(change)

    def get_file_content(self, file: Union[Path, str]) -> str:
        if isinstance(file, str):
            file = uri_to_path(file)
        if file not in self.__output_contents:
            self.__output_contents[file] = file.read_text(encoding="utf-8")
        return self.__output_contents[file]

    def get_line_pos_from_byte_offset(
        self, file: Path, byte_offset: int
    ) -> Tuple[int, int]:
        if file not in self.__line_indexes:
            self.__setup_line_index(file)

        encoded_lines = self.__line_indexes[file]
        line_num = _binary_search(encoded_lines, byte_offset)
        line_data, prefix_sum = encoded_lines[line_num]
        line_offset = byte_offset - prefix_sum
        return line_num, line_offset

    def get_byte_offset_from_line_pos(self, file: Path, line: int, col: int) -> int:
        if file not in self.__line_indexes:
            self.__setup_line_index(file)

        encoded_lines = self.__line_indexes[file]
        line_bytes, prefix = encoded_lines[line]
        line_offset = len(line_bytes.decode("utf-8")[:col].encode("utf-8"))
        return prefix + line_offset

    def __compile(self, files: Collection[Path], modified_files: Mapping[Path, str]):
        out: List[Tuple[CompilationUnit, SolcOutput]] = asyncio.run(
            self.__compiler.compile(
                files,
                [SolcOutputSelectionEnum.AST],
                write_artifacts=False,
                reuse_latest_artifacts=False,
                modified_files=modified_files,
            )
        )

        for cu, solc_output in out:
            self.__errors.update(solc_output.errors)
            for file in cu.files:
                self.__processed_files.add(file)
                if file in self.__line_indexes:
                    self.__line_indexes.pop(file)
            errored = any(
                error.severity == SolcOutputErrorSeverityEnum.ERROR
                for error in solc_output.errors
            )

            for source_unit_name, raw_ast in solc_output.sources.items():
                if errored:
                    # an error occurred during compilation
                    # AST still may be provided, but it must NOT be parsed (pydantic model is not defined for this case)
                    path = cu.source_unit_name_to_path(source_unit_name)
                    if path in modified_files:
                        if path in self.__asts:
                            self.__asts.pop(path)
                        if path in self.__source_units:
                            self.__source_units.pop(path)
                        if path in self.__interval_trees:
                            self.__interval_trees.pop(path)
                else:
                    path = cu.source_unit_name_to_path(source_unit_name)
                    ast = AstSolc.parse_obj(raw_ast.ast)
                    interval_tree = IntervalTree()
                    init = IrInitTuple(
                        path,
                        self.get_file_content(path).encode("utf-8"),
                        cu,
                        interval_tree,
                        self.__ir_reference_resolver,
                    )
                    self.__asts[path] = ast
                    self.__source_units[path] = SourceUnit(init, ast)
                    self.__interval_trees[path] = interval_tree

    def __compilation_loop(self):
        if platform.system() != "Windows" and sys.version_info < (3, 8):
            loop = asyncio.new_event_loop()
            watcher = ThreadedChildWatcher()
            asyncio.set_child_watcher(watcher)
            watcher.attach_loop(loop)

        # perform Solidity files discovery
        project_path = self.__config.project_root_path

        for file in (project_path / "contracts").rglob("*.sol"):
            if file.is_file():
                self.__files[file.resolve()] = file.read_text()

        # perform initial compilation
        self.__compile(self.__files.keys(), {})

        self.__output_contents = self.__files.copy()
        self.output_ready.set()

        while True:
            while not self.__file_changes_queue.empty():
                change = self.__file_changes_queue.get()

                if isinstance(change, DidOpenTextDocumentParams):
                    path = uri_to_path(change.text_document.uri).resolve()
                    self.__files[path] = change.text_document.text
                    self.__opened_files.add(path)
                elif isinstance(change, DidCloseTextDocumentParams):
                    path = uri_to_path(change.text_document.uri).resolve()
                    self.__opened_files.remove(path)
                elif isinstance(change, DidChangeTextDocumentParams):
                    path = uri_to_path(change.text_document.uri).resolve()
                    self.__modified_files.add(path)

                    for content_change in change.content_changes:
                        start = content_change.range.start
                        end = content_change.range.end

                        # str.splitlines() removes empty lines => cannot be used
                        # str.split() removes separators => cannot be used
                        tmp_lines = re.split(r"(\r?\n)", self.__files[path])
                        tmp_lines2: List[str] = []
                        for line in tmp_lines:
                            if line in {"\r\n", "\n"}:
                                tmp_lines2[-1] += line
                            else:
                                tmp_lines2.append(line)

                        lines: List[bytearray] = [
                            bytearray(line.encode(ENCODING)) for line in tmp_lines2
                        ]

                        if start.line == end.line:
                            line = lines[start.line]
                            line[start.character * 2 : end.character * 2] = b""
                            line[
                                start.character * 2 : start.character * 2
                            ] = content_change.text.encode(ENCODING)
                        else:
                            start_line = lines[start.line]
                            end_line = lines[end.line]
                            start_line[
                                start.character * 2 :
                            ] = content_change.text.encode(ENCODING)
                            end_line[: end.character * 2] = b""

                            for i in range(start.line + 1, end.line):
                                lines[i] = bytearray(b"")

                        self.__files[path] = "".join(
                            line.decode(ENCODING) for line in lines
                        )
                else:
                    raise Exception("Unknown change type")

            # run the compilation
            if len(self.__modified_files) > 0:
                modified_files = {
                    path: self.__files[path] for path in self.__modified_files
                }
                self.__compile([], modified_files)

                self.__output_contents.update(self.__files)
                self.__modified_files.clear()

                if self.__file_changes_queue.empty():
                    self.output_ready.set()

    def __setup_line_index(self, file: Path):
        content = self.get_file_content(file)
        tmp_lines = re.split(r"(\r?\n)", content)
        lines: List[str] = []
        for line in tmp_lines:
            if line in {"\r\n", "\n"}:
                lines[-1] += line
            else:
                lines.append(line)

        # UTF-8 encoded lines with prefix length
        encoded_lines: List[Tuple[bytes, int]] = []
        prefix_sum = 0
        for line in lines:
            encoded_line = line.encode("utf-8")
            encoded_lines.append((encoded_line, prefix_sum))
            prefix_sum += len(encoded_line)
        self.__line_indexes[file] = encoded_lines
