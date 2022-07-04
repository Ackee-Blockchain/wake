import asyncio
import logging
import platform
import queue
import re
import sys
import threading
from collections import deque
from pathlib import Path
from typing import Collection, Dict, Iterable, List, Mapping, Set, Tuple, Union

import networkx as nx
from intervaltree import IntervalTree

from woke.ast.ir.meta.source_unit import SourceUnit
from woke.ast.ir.reference_resolver import CallbackParams, ReferenceResolver
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


def _out_edge_bfs(graph: nx.DiGraph, start: Iterable[Path], out: Set[Path]) -> None:
    queue = deque(start)
    out.update(start)

    while len(queue):
        node = queue.pop()
        for out_edge in graph.out_edges(node):
            from_, to = out_edge
            if from_ not in out:
                out.add(from_)
                queue.append(from_)


class LspCompiler:
    __config: WokeConfig
    __file_changes_queue: asyncio.Queue

    __processed_files: Set[Path]

    # accessed from the compilation thread
    # full path -> contents
    __files: Dict[Path, str]
    __opened_files: Set[Path]
    __modified_files: Set[Path]
    __compiler: SolidityCompiler
    __output_contents: Dict[Path, str]
    __interval_trees: Dict[Path, IntervalTree]
    __source_units: Dict[Path, SourceUnit]
    __line_indexes: Dict[Path, List[Tuple[bytes, int]]]

    __ir_reference_resolver: ReferenceResolver

    __output_ready: asyncio.Event

    def __init__(self, config: WokeConfig):
        self.__config = config
        self.__file_changes_queue = asyncio.Queue()
        self.__stop_event = threading.Event()
        self.__processed_files = set()
        self.__files = dict()
        self.__opened_files = set()
        self.__modified_files = set()
        self.__compiler = SolidityCompiler(config)
        self.__interval_trees = {}
        self.__source_units = {}
        self.__line_indexes = {}
        self.__output_contents = dict()
        self.__output_ready = asyncio.Event()

        self.__ir_reference_resolver = ReferenceResolver()

    async def run(self):
        await self.__compilation_loop()

    @property
    def output_ready(self) -> asyncio.Event:
        return self.__output_ready

    @property
    def ir_reference_resolver(self) -> ReferenceResolver:
        return self.__ir_reference_resolver

    @property
    def interval_trees(self) -> Dict[Path, IntervalTree]:
        return self.__interval_trees

    @property
    def source_units(self) -> Dict[Path, SourceUnit]:
        return self.__source_units

    async def add_change(
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
        await self.__file_changes_queue.put(change)

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

    async def __compile(
        self, files: Collection[Path], modified_files: Mapping[Path, str]
    ):
        out: List[Tuple[CompilationUnit, SolcOutput]] = await self.__compiler.compile(
            files,
            [SolcOutputSelectionEnum.AST],
            write_artifacts=False,
            reuse_latest_artifacts=False,
            modified_files=modified_files,
            maximize_compilation_units=True,
        )
        self.__output_contents.update(self.__files)

        errors_per_file: Dict[Path, List[SolcOutputError]] = {}

        for cu, solc_output in out:
            for file in cu.files:
                self.__processed_files.add(file)
                errors_per_file[file] = []
                if file in self.__line_indexes:
                    self.__line_indexes.pop(file)

            errored_files: Set[Path] = set()

            for error in solc_output.errors:
                if error.source_location is not None:
                    path = cu.source_unit_name_to_path(error.source_location.file)
                    errors_per_file[path].append(error)

                    if error.severity == SolcOutputErrorSeverityEnum.ERROR:
                        errored_files.add(path)

            _out_edge_bfs(cu.graph, errored_files, errored_files)

            # modified files and files that import modified files (even indirectly)
            recompiled_files: Set[Path] = set()
            _out_edge_bfs(cu.graph, modified_files, recompiled_files)

            for file in errored_files:
                # an error occurred during compilation
                # AST still may be provided, but it must NOT be parsed (pydantic model is not defined for this case)
                if file in self.__source_units:
                    self.__source_units.pop(file)
                if file in self.__interval_trees:
                    self.__interval_trees.pop(file)

            for source_unit_name, raw_ast in solc_output.sources.items():
                path = cu.source_unit_name_to_path(source_unit_name)
                if path in errored_files:
                    continue
                ast = AstSolc.parse_obj(raw_ast.ast)

                self.__ir_reference_resolver.index_nodes(ast, path, cu.blake2b_digest)

                if path not in files and path not in recompiled_files:
                    continue

                interval_tree = IntervalTree()
                init = IrInitTuple(
                    path,
                    self.get_file_content(path).encode("utf-8"),
                    cu,
                    interval_tree,
                    self.__ir_reference_resolver,
                )
                self.__source_units[path] = SourceUnit(init, ast)
                self.__interval_trees[path] = interval_tree

            self.__ir_reference_resolver.run_post_process_callbacks(
                CallbackParams(source_units=self.__source_units)
            )

    async def __compilation_loop(self):
        # perform Solidity files discovery
        project_path = self.__config.project_root_path

        for file in project_path.rglob("**/*.sol"):
            if "node_modules" not in file.parts and file.is_file():
                self.__files[file.resolve()] = file.read_text()

        # perform initial compilation
        await self.__compile(self.__files.keys(), {})

        self.__output_contents = self.__files.copy()
        self.output_ready.set()

        while True:
            change = await self.__file_changes_queue.get()
            while True:
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
                try:
                    change = self.__file_changes_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

            # run the compilation
            if len(self.__modified_files) > 0:
                modified_files = {
                    path: self.__files[path] for path in self.__modified_files
                }
                await self.__compile([], modified_files)

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
