from __future__ import annotations

import asyncio
import difflib
import logging
import re
import threading
import time
from collections import deque
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    AbstractSet,
    Deque,
    Dict,
    Iterable,
    List,
    NamedTuple,
    Optional,
    Set,
    Tuple,
    Union,
)

from woke.compiler.exceptions import CompilationError

from ..analysis.detectors import detect
from ..core.solidity_version import SolidityVersionRange, SolidityVersionRanges
from ..utils import StrEnum
from ..utils.file_utils import is_relative_to

if TYPE_CHECKING:
    from .server import LspServer

import networkx as nx
from intervaltree import IntervalTree

from woke.ast.ir.meta.source_unit import SourceUnit
from woke.ast.ir.reference_resolver import CallbackParams, ReferenceResolver
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import AstSolc
from woke.compiler import SolcOutput, SolcOutputSelectionEnum
from woke.compiler.compilation_unit import CompilationUnit
from woke.compiler.compiler import SolidityCompiler
from woke.compiler.solc_frontend import SolcOutputError, SolcOutputErrorSeverityEnum
from woke.config import WokeConfig
from woke.lsp.document_sync import (
    DidChangeTextDocumentParams,
    DidCloseTextDocumentParams,
    DidOpenTextDocumentParams,
)
from woke.lsp.utils.uri import path_to_uri, uri_to_path

from ..svm import SolcVersionManager
from .common_structures import (
    CreateFilesParams,
    DeleteFile,
    DeleteFilesParams,
    Diagnostic,
    DiagnosticRelatedInformation,
    DiagnosticSeverity,
    DocumentUri,
    Location,
    MessageType,
    Position,
    Range,
    RenameFilesParams,
)

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


def _out_edge_bfs(cu: CompilationUnit, start: Iterable[Path], out: Set[Path]) -> None:
    processed: Set[str] = set()
    for path in start:
        processed.update(cu.path_to_source_unit_names(path))
    out.update(start)

    queue: Deque[str] = deque(processed)
    while len(queue):
        node = queue.pop()
        for out_edge in cu.graph.out_edges(node):
            from_, to = out_edge
            if to not in processed:
                processed.add(to)
                queue.append(to)
                out.add(cu.source_unit_name_to_path(to))


class VersionedFile(NamedTuple):
    text: str
    version: Optional[int]


class CustomFileChangeCommand(StrEnum):
    FORCE_RECOMPILE = "force_recompile"
    FORCE_RERUN_DETECTORS = "force_rerun_detectors"


class LspCompiler:
    __config: WokeConfig
    __svm: SolcVersionManager
    __server: LspServer
    __file_changes_queue: asyncio.Queue
    __diagnostic_queue: asyncio.Queue
    __discovered_files: Set[Path]
    __deleted_files: Set[Path]
    __opened_files: Dict[Path, VersionedFile]
    __modified_files: Set[Path]
    __force_compile_files: Set[Path]
    __compiler: SolidityCompiler
    __output_contents: Dict[Path, VersionedFile]
    __compilation_errors: Dict[Path, Set[Diagnostic]]
    __last_successful_compilation_contents: Dict[Path, VersionedFile]
    __interval_trees: Dict[Path, IntervalTree]
    __source_units: Dict[Path, SourceUnit]
    __last_compilation_interval_trees: Dict[Path, IntervalTree]
    __last_compilation_source_units: Dict[Path, SourceUnit]
    __last_graph: nx.DiGraph
    __line_indexes: Dict[Path, List[Tuple[bytes, int]]]
    __perform_files_discovery: bool
    __force_run_detectors: bool

    __ir_reference_resolver: ReferenceResolver

    __output_ready: asyncio.Event

    def __init__(
        self,
        server: LspServer,
        diagnostic_queue: asyncio.Queue,
        perform_files_discovery: bool,
    ):
        self.__server = server
        self.__file_changes_queue = asyncio.Queue()
        self.__diagnostic_queue = diagnostic_queue
        self.__stop_event = threading.Event()
        self.__discovered_files = set()
        self.__deleted_files = set()
        self.__opened_files = {}
        self.__modified_files = set()
        self.__force_compile_files = set()
        self.__interval_trees = {}
        self.__source_units = {}
        self.__last_compilation_interval_trees = {}
        self.__last_compilation_source_units = {}
        self.__last_graph = nx.DiGraph()
        self.__line_indexes = {}
        self.__output_contents = dict()
        self.__compilation_errors = dict()
        self.__last_successful_compilation_contents = dict()
        self.__output_ready = asyncio.Event()
        self.__perform_files_discovery = perform_files_discovery
        self.__force_run_detectors = False

        self.__ir_reference_resolver = ReferenceResolver()

    async def run(self, config: WokeConfig):
        self.__config = config
        self.__svm = SolcVersionManager(config)
        self.__compiler = SolidityCompiler(config)
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

    @property
    def last_compilation_interval_trees(self) -> Dict[Path, IntervalTree]:
        return self.__last_compilation_interval_trees

    @property
    def last_compilation_source_units(self) -> Dict[Path, SourceUnit]:
        return self.__last_compilation_source_units

    @property
    def last_graph(self) -> nx.DiGraph:
        return self.__last_graph

    @lru_cache(maxsize=128)
    def _compute_diff_interval_tree(
        self, a: VersionedFile, b: VersionedFile
    ) -> IntervalTree:
        seq_matcher = difflib.SequenceMatcher(None, a.text, b.text)
        interval_tree = IntervalTree()
        for tag, i1, i2, j1, j2 in seq_matcher.get_opcodes():
            if tag == "equal":
                continue
            interval_tree.addi(i1, i2 + 1, (tag, j1, j2 + 1))
        return interval_tree

    def get_last_compilation_forward_changes(
        self, path: Path
    ) -> Optional[IntervalTree]:
        if path not in self.__last_successful_compilation_contents:
            return None
        return self._compute_diff_interval_tree(
            self.__last_successful_compilation_contents[path],
            self.get_compiled_file(path),
        )

    def get_last_compilation_backward_changes(
        self, path: Path
    ) -> Optional[IntervalTree]:
        if path not in self.__last_successful_compilation_contents:
            return None
        return self._compute_diff_interval_tree(
            self.get_compiled_file(path),
            self.__last_successful_compilation_contents[path],
        )

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
        self.output_ready.clear()
        await self.__file_changes_queue.put(change)

    async def force_recompile(self) -> None:
        self.__output_ready.clear()
        await self.__file_changes_queue.put(CustomFileChangeCommand.FORCE_RECOMPILE)

    async def force_rerun_detectors(self) -> None:
        await self.__file_changes_queue.put(
            CustomFileChangeCommand.FORCE_RERUN_DETECTORS
        )

    def get_compiled_file(self, file: Union[Path, str]) -> VersionedFile:
        if isinstance(file, str):
            file = uri_to_path(file)
        if file not in self.__output_contents:
            self.__output_contents[file] = VersionedFile(
                file.read_bytes().decode(encoding="utf-8"), None
            )
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

    def get_range_from_byte_offsets(
        self, file: Path, byte_offsets: Tuple[int, int]
    ) -> Range:
        start_line, start_column = self.get_line_pos_from_byte_offset(
            file, byte_offsets[0]
        )
        end_line, end_column = self.get_line_pos_from_byte_offset(file, byte_offsets[1])

        return Range(
            start=Position(line=start_line, character=start_column),
            end=Position(line=end_line, character=end_column),
        )

    def get_byte_offset_from_line_pos(self, file: Path, line: int, col: int) -> int:
        if file not in self.__line_indexes:
            self.__setup_line_index(file)

        encoded_lines = self.__line_indexes[file]
        line_bytes, prefix = encoded_lines[line]
        line_offset = len(line_bytes.decode("utf-8")[:col].encode("utf-8"))
        return prefix + line_offset

    async def _handle_change(
        self,
        change: Union[
            DidOpenTextDocumentParams,
            DidCloseTextDocumentParams,
            DidChangeTextDocumentParams,
            None,
        ],
    ) -> None:
        if isinstance(change, CustomFileChangeCommand):
            if change == CustomFileChangeCommand.FORCE_RECOMPILE:
                for file in self.__discovered_files:
                    # clear diagnostics
                    await self.__diagnostic_queue.put((file, set()))

                self.__discovered_files.clear()
                self.__compilation_errors.clear()
                if self.__perform_files_discovery:
                    for file in self.__config.project_root_path.rglob("**/*.sol"):
                        if not self.__file_ignored(file) and file.is_file():
                            self.__discovered_files.add(file.resolve())

                for file in self.__opened_files.keys():
                    if not self.__file_ignored(file):
                        self.__discovered_files.add(file)

                self.__force_compile_files.update(self.__discovered_files)
            elif change == CustomFileChangeCommand.FORCE_RERUN_DETECTORS:
                self.__force_run_detectors = True
        elif isinstance(change, CreateFilesParams):
            for file in change.files:
                path = uri_to_path(file.uri)
                if (
                    path not in self.__discovered_files
                    and not self.__file_ignored(path)
                    and path.is_file()
                    and path.suffix == ".sol"
                ):
                    self.__discovered_files.add(path)
                    self.__force_compile_files.add(path)
        elif isinstance(change, RenameFilesParams):
            for rename in change.files:
                old_path = uri_to_path(rename.old_uri)
                self.__deleted_files.add(old_path)
                self.__discovered_files.discard(old_path)

                new_path = uri_to_path(rename.new_uri)
                if (
                    new_path not in self.__discovered_files
                    and not self.__file_ignored(new_path)
                    and new_path.is_file()
                    and new_path.suffix == ".sol"
                ):
                    self.__discovered_files.add(new_path)
                    self.__force_compile_files.add(new_path)
        elif isinstance(change, DeleteFilesParams):
            for delete in change.files:
                path = uri_to_path(delete.uri)
                self.__deleted_files.add(path)
                self.__discovered_files.discard(path)
        elif isinstance(change, DidOpenTextDocumentParams):
            path = uri_to_path(change.text_document.uri).resolve()
            self.__opened_files[path] = VersionedFile(
                change.text_document.text, change.text_document.version
            )
            if (
                path not in self.__discovered_files
                and not self.__file_ignored(path)
                and path.is_file()
                and path.suffix == ".sol"
            ):
                self.__discovered_files.add(path)
                self.__force_compile_files.add(path)
            elif change.text_document.text != self.get_compiled_file(path).text:
                self.__force_compile_files.add(path)
            else:
                self.__output_contents[path] = self.__opened_files[path]

        elif isinstance(change, DidCloseTextDocumentParams):
            pass
        elif isinstance(change, DidChangeTextDocumentParams):
            path = uri_to_path(change.text_document.uri).resolve()
            self.__modified_files.add(path)

            for content_change in change.content_changes:
                start = content_change.range.start
                end = content_change.range.end

                # str.splitlines() removes empty lines => cannot be used
                # str.split() removes separators => cannot be used
                tmp_lines = re.split(r"(\r?\n)", self.__opened_files[path].text)
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
                    start_line[start.character * 2 :] = content_change.text.encode(
                        ENCODING
                    )
                    end_line[: end.character * 2] = b""

                    for i in range(start.line + 1, end.line):
                        lines[i] = bytearray(b"")

                self.__opened_files[path] = VersionedFile(
                    "".join(line.decode(ENCODING) for line in lines),
                    change.text_document.version,
                )
        else:
            raise Exception("Unknown change type")

    async def __compile(
        self,
        files_to_compile: AbstractSet[Path],
        full_compile: bool = True,
    ) -> None:
        target_version = self.__config.compiler.solc.target_version
        min_version = self.__config.min_solidity_version
        max_version = self.__config.max_solidity_version
        if target_version is not None and target_version < min_version:
            await self.__server.log_message(
                f"The minimum supported version of Solidity is {min_version}. Version {target_version} is selected in settings.",
                MessageType.ERROR,
            )
            for file in self.__discovered_files:
                # clear diagnostics
                await self.__diagnostic_queue.put((file, set()))
            self.__interval_trees.clear()
            self.__source_units.clear()
            return
        if target_version is not None and target_version > max_version:
            await self.__server.log_message(
                f"The maximum supported version of Solidity is {max_version}. Version {target_version} is selected in settings.",
                MessageType.ERROR,
            )
            for file in self.__discovered_files:
                # clear diagnostics
                await self.__diagnostic_queue.put((file, set()))
            self.__interval_trees.clear()
            self.__source_units.clear()
            return

        try:
            if full_compile:
                graph, _ = self.__compiler.build_graph(
                    self.__discovered_files,
                    {path: info.text for path, info in self.__opened_files.items()},
                    True,
                )
                self.__last_graph = graph
            else:
                graph, _ = self.__compiler.build_graph(
                    files_to_compile,
                    {path: info.text for path, info in self.__opened_files.items()},
                    True,
                )
        except CompilationError as e:
            await self.__server.log_message(str(e), MessageType.ERROR)
            for file in self.__discovered_files:
                # clear diagnostics
                await self.__diagnostic_queue.put((file, set()))
            self.__interval_trees.clear()
            self.__source_units.clear()
            return

        compilation_units = self.__compiler.build_compilation_units_maximize(graph)

        # filter out only compilation units that need to be compiled
        compilation_units = [
            cu
            for cu in compilation_units
            if (cu.files & files_to_compile)
            or cu.contains_unresolved_file(self.__deleted_files, self.__config)
        ]
        if len(compilation_units) == 0:
            return

        build_settings = self.__compiler.create_build_settings(
            [SolcOutputSelectionEnum.AST]
        )

        # optimization - merge compilation units that can be compiled together
        if all(len(cu.versions) for cu in compilation_units):
            compilation_units = sorted(
                compilation_units, key=lambda cu: cu.versions.version_ranges[0].lower
            )

            merged_compilation_units: List[CompilationUnit] = []
            source_unit_names: Set = set()
            versions = SolidityVersionRanges(
                [SolidityVersionRange(None, None, None, None)]
            )

            for cu in compilation_units:
                if versions & cu.versions:
                    source_unit_names |= cu.source_unit_names
                    versions &= cu.versions
                else:
                    merged_compilation_units.append(
                        CompilationUnit(
                            graph.subgraph(source_unit_names).copy(),
                            versions,
                        )
                    )
                    source_unit_names = set(cu.source_unit_names)
                    versions = cu.versions

            merged_compilation_units.append(
                CompilationUnit(
                    graph.subgraph(source_unit_names).copy(),
                    versions,
                )
            )

            compilation_units = merged_compilation_units

        target_versions = []
        skipped_compilation_units = []
        for compilation_unit in compilation_units:
            target_version = self.__config.compiler.solc.target_version
            if target_version is not None:
                if target_version not in compilation_unit.versions:
                    await self.__server.log_message(
                        f"Unable to compile the following files with solc version `{target_version}` set in config:\n"
                        + "\n".join(
                            path_to_uri(path) for path in compilation_unit.files
                        ),
                        MessageType.ERROR,
                    )
                    skipped_compilation_units.append(compilation_unit)
                    continue
            else:
                # use the latest matching version
                matching_versions = [
                    version
                    for version in reversed(self.__svm.list_all())
                    if version in compilation_unit.versions
                ]
                if len(matching_versions) == 0:
                    await self.__server.log_message(
                        f"Unable to find a matching version of Solidity for the following files:\n"
                        + "\n".join(
                            path_to_uri(path) for path in compilation_unit.files
                        ),
                        MessageType.ERROR,
                    )
                    skipped_compilation_units.append(compilation_unit)
                    continue
                try:
                    target_version = next(
                        version
                        for version in matching_versions
                        if version <= max_version
                    )
                except StopIteration:
                    await self.__server.log_message(
                        f"The maximum supported version of Solidity is {max_version}, unable to compile the following files:\n"
                        + "\n".join(
                            path_to_uri(path) for path in compilation_unit.files
                        ),
                        MessageType.ERROR,
                    )
                    skipped_compilation_units.append(compilation_unit)
                    continue

                if target_version < min_version:
                    await self.__server.log_message(
                        f"The minimum supported version of Solidity is {min_version}, unable to compile the following files:\n"
                        + "\n".join(
                            path_to_uri(path) for path in compilation_unit.files
                        ),
                        MessageType.ERROR,
                    )
                    skipped_compilation_units.append(compilation_unit)
                    continue
            target_versions.append(target_version)

        for version in set(target_versions):
            if not self.__svm.installed(version):
                progress_token = await self.__server.progress_begin(
                    "Downloading", f"solc {version}", 0
                )
                if progress_token is not None:

                    async def on_progress(downloaded: int, total: int) -> None:
                        assert progress_token is not None
                        await self.__server.progress_report(
                            progress_token,
                            f"solc {version}",
                            (100 * downloaded) // total,
                        )

                    await self.__svm.install(version, progress=on_progress)
                    await self.__server.progress_end(progress_token)
                else:
                    await self.__svm.install(version)

        for compilation_unit in skipped_compilation_units:
            for file in compilation_unit.files:
                # clear diagnostics
                await self.__diagnostic_queue.put((file, set()))
                self.__interval_trees.pop(file, None)
                self.__source_units.pop(file, None)
            compilation_units.remove(compilation_unit)

        progress_token = await self.__server.progress_begin(
            "Compiling", f"0/{len(compilation_units)}", 0
        )

        tasks = []
        for compilation_unit, target_version in zip(compilation_units, target_versions):
            task = self.__server.create_task(
                self.__compiler.compile_unit_raw(
                    compilation_unit,
                    target_version,
                    build_settings,
                )
            )
            tasks.append(task)

        # wait for compilation of all compilation units
        try:
            ret = await asyncio.gather(*tasks)
        except Exception as e:
            for task in tasks:
                task.cancel()
            await self.__server.log_message(str(e), MessageType.ERROR)
            if progress_token is not None:
                await self.__server.progress_end(progress_token)

            for file in self.__discovered_files:
                # clear diagnostics
                await self.__diagnostic_queue.put((file, set()))
            self.__interval_trees.clear()
            self.__source_units.clear()
            return

        errors_without_location: Set[SolcOutputError] = set()
        errors_per_file: Dict[Path, Set[Diagnostic]] = deepcopy(
            self.__compilation_errors
        )

        for cu, solc_output in zip(compilation_units, ret):
            for file in cu.files:
                errors_per_file[file] = set()
            for error in solc_output.errors:
                if error.source_location is None:
                    errors_without_location.add(error)

        for error in errors_without_location:
            if error.severity == SolcOutputErrorSeverityEnum.ERROR:
                error_type = MessageType.ERROR
            elif error.severity == SolcOutputErrorSeverityEnum.WARNING:
                error_type = MessageType.WARNING
            elif error.severity == SolcOutputErrorSeverityEnum.INFO:
                error_type = MessageType.INFO
            else:
                error_type = MessageType.LOG
            await self.__server.show_message(error.message, error_type)
            await self.__server.log_message(error.message, error_type)

        if (
            any(
                e.severity == SolcOutputErrorSeverityEnum.ERROR
                for e in errors_without_location
            )
            > 0
        ):
            if progress_token is not None:
                await self.__server.progress_end(progress_token)

            for file in self.__discovered_files:
                # clear diagnostics
                await self.__diagnostic_queue.put((file, set()))
            self.__interval_trees.clear()
            self.__source_units.clear()
            return

        files_to_recompile = set(files_to_compile)
        processed_files: Set[Path] = set()

        for deleted_file in self.__deleted_files:
            await self.__diagnostic_queue.put((deleted_file, []))
            if deleted_file in self.__source_units:
                self.__ir_reference_resolver.run_destroy_callbacks(deleted_file)
                self.__source_units.pop(deleted_file)

        for cu_index, (cu, solc_output) in enumerate(zip(compilation_units, ret)):
            for file in cu.files:
                if file in self.__line_indexes:
                    self.__line_indexes.pop(file)
                if file in self.__opened_files:
                    self.__output_contents[file] = self.__opened_files[file]

            errored_files: Set[Path] = set()

            for error in solc_output.errors:
                if error.source_location is not None:
                    path = cu.source_unit_name_to_path(error.source_location.file)
                    errors_per_file[path].add(
                        self.__solc_error_to_diagnostic(error, path)
                    )
                    if error.severity == SolcOutputErrorSeverityEnum.ERROR:
                        errored_files.add(path)

            _out_edge_bfs(cu, errored_files, errored_files)

            # files requested to be compiled and files that import these files (even indirectly)
            recompiled_files: Set[Path] = set()
            _out_edge_bfs(cu, files_to_compile & cu.files, recompiled_files)

            for file in errored_files:
                files_to_recompile.discard(file)
                # an error occurred during compilation
                # AST still may be provided, but it must NOT be parsed (pydantic model is not defined for this case)
                if file in self.__source_units:
                    self.__ir_reference_resolver.run_destroy_callbacks(file)
                    self.__source_units.pop(file)
                if file in self.__interval_trees:
                    self.__interval_trees.pop(file)

            if len(errored_files) == 0:
                for source_unit_name, raw_ast in solc_output.sources.items():
                    path = cu.source_unit_name_to_path(source_unit_name)
                    if path in errored_files or raw_ast.ast is None:
                        continue
                    ast = AstSolc.parse_obj(raw_ast.ast)

                    self.__ir_reference_resolver.index_nodes(ast, path, cu.hash)

                    files_to_recompile.discard(path)

                    # give a chance to other tasks (LSP requests) to be processed
                    await asyncio.sleep(0)

                    if (
                        path in self.__source_units and path not in recompiled_files
                    ) or path in processed_files:
                        continue
                    processed_files.add(path)

                    interval_tree = IntervalTree()
                    init = IrInitTuple(
                        path,
                        self.get_compiled_file(path).text.encode("utf-8"),
                        cu,
                        interval_tree,
                        self.__ir_reference_resolver,
                        None,
                    )
                    self.__ir_reference_resolver.run_destroy_callbacks(path)
                    self.__source_units[path] = SourceUnit(init, ast)
                    self.__interval_trees[path] = interval_tree

                    self.__last_compilation_source_units[path] = self.__source_units[
                        path
                    ]
                    self.__last_compilation_interval_trees[
                        path
                    ] = self.__interval_trees[path]

                    if path in self.__opened_files:
                        self.__last_successful_compilation_contents[
                            path
                        ] = self.__opened_files[path]
                    else:
                        self.__last_successful_compilation_contents[
                            path
                        ] = VersionedFile(
                            cu.graph.nodes[source_unit_name]["content"], None
                        )

            self.__ir_reference_resolver.run_post_process_callbacks(
                CallbackParams(
                    interval_trees=self.__interval_trees,
                    source_units=self.__source_units,
                )
            )

            if progress_token is not None:
                await self.__server.progress_report(
                    progress_token,
                    f"{cu_index + 1}/{len(compilation_units)}",
                    ((cu_index + 1) * 100) // len(compilation_units),
                )

        if progress_token is not None:
            await self.__server.progress_end(progress_token)

        self.__compilation_errors = deepcopy(errors_per_file)

        # diagnostics (compiler errors and warnings + detections) are sent in this function
        await self.__run_detectors()

        if len(files_to_recompile) > 0:
            # avoid infinite recursion
            if files_to_recompile != files_to_compile or full_compile:
                await self.__compile(files_to_recompile, False)

    async def __run_detectors(self):
        errors_per_file: Dict[Path, Set[Diagnostic]] = deepcopy(
            self.__compilation_errors
        )

        if self.__config.lsp.detectors.enable:
            for detection in detect(self.__config, self.__source_units):
                file = detection.result.ir_node.file
                if len(detection.result.related_info) > 0:
                    related_info = [
                        DiagnosticRelatedInformation(
                            location=Location(
                                uri=DocumentUri(path_to_uri(info.ir_node.file)),
                                range=self.get_range_from_byte_offsets(
                                    info.ir_node.file,
                                    info.lsp_range
                                    if info.lsp_range is not None
                                    else info.ir_node.byte_location,
                                ),
                            ),
                            message=info.message,
                        )
                        for info in detection.result.related_info
                    ]
                else:
                    related_info = None

                if file not in errors_per_file:
                    errors_per_file[file] = set()
                errors_per_file[file].add(
                    Diagnostic(
                        range=self.get_range_from_byte_offsets(
                            file,
                            detection.result.lsp_range
                            if detection.result.lsp_range is not None
                            else detection.result.ir_node.byte_location,
                        ),
                        severity=DiagnosticSeverity.WARNING,
                        source="Woke",
                        message=detection.result.message,
                        code=detection.code,
                        related_information=related_info,
                    )
                )

        for path, errors in errors_per_file.items():
            await self.__diagnostic_queue.put((path, errors))

    async def __compilation_loop(self):
        if self.__perform_files_discovery:
            # perform Solidity files discovery
            for file in self.__config.project_root_path.rglob("**/*.sol"):
                if not self.__file_ignored(file) and file.is_file():
                    self.__discovered_files.add(file.resolve())

            # perform initial compilation
            await self.__compile(self.__discovered_files)

        if self.__file_changes_queue.empty():
            self.output_ready.set()

        while True:
            change = await self.__file_changes_queue.get()
            start = time.perf_counter()
            await self._handle_change(change)
            while True:
                try:
                    change = self.__file_changes_queue.get_nowait()
                    start = time.perf_counter()
                    await self._handle_change(change)
                except asyncio.QueueEmpty:
                    if (
                        time.perf_counter() - start
                        > self.__config.lsp.compilation_delay
                    ):
                        break
                    await asyncio.sleep(0.1)

            # run the compilation
            if (
                len(self.__force_compile_files) > 0
                or len(self.__modified_files) > 0
                or len(self.__deleted_files) > 0
            ):
                await self.__compile(
                    self.__force_compile_files.union(self.__modified_files)
                )

                self.__force_compile_files.clear()
                self.__modified_files.clear()
                self.__deleted_files.clear()

            if self.__force_run_detectors:
                await self.__run_detectors()
                self.__force_run_detectors = False

            if self.__file_changes_queue.empty():
                self.output_ready.set()

    def __setup_line_index(self, file: Path):
        content = self.get_compiled_file(file).text
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

    def __solc_error_to_diagnostic(
        self, error: SolcOutputError, path: Path
    ) -> Diagnostic:
        assert error.source_location is not None
        if error.severity == SolcOutputErrorSeverityEnum.ERROR:
            severity = DiagnosticSeverity.ERROR
        elif error.severity == SolcOutputErrorSeverityEnum.WARNING:
            severity = DiagnosticSeverity.WARNING
        else:
            severity = DiagnosticSeverity.INFORMATION

        if error.source_location.start >= 0 and error.source_location.end >= 0:
            range_ = self.get_range_from_byte_offsets(
                path, (error.source_location.start, error.source_location.end)
            )
        else:
            range_ = Range(
                start=Position(line=0, character=0),
                end=Position(line=0, character=0),
            )

        return Diagnostic(
            range=range_,
            severity=severity,
            code=error.error_code,
            source="Woke(solc)",
            message=error.message,
        )

    def __file_ignored(self, path: Path) -> bool:
        return any(
            is_relative_to(path, p) for p in self.__config.compiler.solc.ignore_paths
        )
