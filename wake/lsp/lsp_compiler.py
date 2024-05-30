from __future__ import annotations

import asyncio
import difflib
import multiprocessing
import multiprocessing.connection
import queue
import re
import threading
import time
from collections import defaultdict, deque
from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    AbstractSet,
    Any,
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

import packaging.version

from wake.compiler.exceptions import CompilationError

from ..compiler.build_data_model import (
    CompilationUnitBuildInfo,
    ProjectBuild,
    ProjectBuildInfo,
    SourceUnitInfo,
)
from ..core.solidity_version import SolidityVersionRange, SolidityVersionRanges
from ..core.wake_comments import error_commented_out
from ..utils import StrEnum, get_package_version
from ..utils.file_utils import is_relative_to
from .exceptions import LspError
from .lsp_data_model import LspModel
from .methods import RequestMethodEnum
from .protocol_structures import ErrorCodes
from .subprocess_runner import (
    SubprocessCommandType,
    run_detectors_subprocess,
    run_printers_subprocess,
)

if TYPE_CHECKING:
    from .server import LspServer

import networkx as nx
from intervaltree import IntervalTree

from wake.compiler import SolcOutputSelectionEnum
from wake.compiler.compilation_unit import CompilationUnit
from wake.compiler.compiler import SolidityCompiler
from wake.compiler.solc_frontend import (
    SolcInputSettings,
    SolcOutputError,
    SolcOutputErrorSeverityEnum,
)
from wake.config import WakeConfig
from wake.core import get_logger
from wake.core.lsp_provider import (
    CodeLensOptions,
    CommandAbc,
    HoverOptions,
    InlayHintOptions,
)
from wake.ir import SourceUnit
from wake.ir.ast import AstSolc
from wake.ir.reference_resolver import CallbackParams, ReferenceResolver
from wake.ir.utils import IrInitTuple
from wake.lsp.document_sync import (
    DidChangeTextDocumentParams,
    DidCloseTextDocumentParams,
    DidOpenTextDocumentParams,
)
from wake.lsp.utils.uri import path_to_uri, uri_to_path

from ..svm import SolcVersionManager
from .common_structures import (
    CreateFilesParams,
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

logger = get_logger(__name__)


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
        for out_edge in cu.graph.out_edges(
            node  # pyright: ignore reportGeneralTypeIssues
        ):
            from_, to = out_edge  # pyright: ignore reportGeneralTypeIssues
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
    FORCE_RERUN_PRINTERS = "force_rerun_printers"


@dataclass
class ConfigUpdate:
    new_config: Dict
    removed_options: Set
    local_config_path: Path


@dataclass
class Subprocess:
    process: Optional[multiprocessing.Process]
    in_queue: multiprocessing.Queue
    out_queue: multiprocessing.Queue
    command_id: int
    responses: Dict[int, Tuple[SubprocessCommandType, Any]]
    code_lenses: Dict[Path, Dict[Tuple[int, int], Set[CodeLensOptions]]]
    hovers: Dict[Path, Dict[Tuple[int, int], Set[HoverOptions]]]
    inlay_hints: Dict[Path, Dict[int, List[InlayHintOptions]]]


class CompilationErrorAdditionalInfo(LspModel):
    severity: SolcOutputErrorSeverityEnum
    ignored: bool
    source_unit_name: str

    def __members(self) -> Tuple:
        return (
            self.severity,
            self.ignored,
            self.source_unit_name,
        )

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.__members() == other.__members()
        return NotImplemented

    def __hash__(self):
        return hash(self.__members())


class LspCompiler:
    __config: WakeConfig
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
    __last_build_settings: SolcInputSettings
    __line_indexes: Dict[Path, List[Tuple[bytes, int]]]
    __perform_files_discovery: bool
    __force_run_detectors: bool
    __force_run_printers: bool
    __wake_version: str
    __latest_errors_per_cu: Dict[bytes, Set[SolcOutputError]]
    __ignored_detections_supported: bool

    __ir_reference_resolver: ReferenceResolver

    __output_ready: asyncio.Event

    __detectors_subprocess: Subprocess
    __printers_subprocess: Subprocess

    __detectors_task: Optional[asyncio.Task]
    __printers_task: Optional[asyncio.Task]

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
        self.__last_build_settings = (
            SolcInputSettings()
        )  # pyright: ignore reportGeneralTypeIssues
        self.__line_indexes = {}
        self.__output_contents = dict()
        self.__compilation_errors = dict()
        self.__last_successful_compilation_contents = dict()
        self.__output_ready = asyncio.Event()
        self.__perform_files_discovery = perform_files_discovery
        self.__force_run_detectors = False
        self.__force_run_printers = False
        self.__wake_version = get_package_version("eth-wake")
        self.__latest_errors_per_cu = {}

        try:
            if server.tfs_version is not None and packaging.version.parse(
                server.tfs_version
            ) > packaging.version.parse("1.10.3"):
                self.__ignored_detections_supported = True
            else:
                self.__ignored_detections_supported = False
        except packaging.version.InvalidVersion:
            self.__ignored_detections_supported = False

        self.__ir_reference_resolver = ReferenceResolver()
        self.__detectors_task = None
        self.__printers_task = None

        self.__detectors_subprocess = Subprocess(
            None,
            multiprocessing.Queue(),
            multiprocessing.Queue(),
            0,
            {},
            {},
            {},
            {},
        )
        self.__printers_subprocess = Subprocess(
            None,
            multiprocessing.Queue(),
            multiprocessing.Queue(),
            0,
            {},
            {},
            {},
            {},
        )

        self.__detector_code_lenses = {}
        self.__printer_code_lenses = {}
        self.__detector_hovers = {}
        self.__printer_hovers = {}
        self.__detector_inlay_hints = {}
        self.__printer_inlay_hints = {}

    async def run(self, config: WakeConfig):
        self.__config = config
        self.__svm = SolcVersionManager(config)
        self.__compiler = SolidityCompiler(config)

        # TODO process recovery?
        self.__detectors_subprocess.process = multiprocessing.Process(
            target=run_detectors_subprocess,
            args=(
                self.__detectors_subprocess.out_queue,
                self.__detectors_subprocess.in_queue,
                config,
                self.__ignored_detections_supported,
            ),
        )
        self.__detectors_subprocess.process.start()

        self.__printers_subprocess.process = multiprocessing.Process(
            target=run_printers_subprocess,
            args=(
                self.__printers_subprocess.out_queue,
                self.__printers_subprocess.in_queue,
                config,
            ),
        )
        self.__printers_subprocess.process.start()

        await self.__compilation_loop()

    async def stop(self):
        if self.__detectors_subprocess.process is not None:
            self.__detectors_subprocess.process.terminate()
            await asyncio.sleep(0.5)

            if self.__detectors_subprocess.process.is_alive():
                self.__detectors_subprocess.process.kill()

        if self.__printers_subprocess.process is not None:
            self.__printers_subprocess.process.terminate()
            await asyncio.sleep(0.5)

            if self.__printers_subprocess.process.is_alive():
                self.__printers_subprocess.process.kill()

    @staticmethod
    def send_subprocess_command(
        subprocess: Subprocess, command: SubprocessCommandType, data: Any
    ) -> int:
        subprocess.out_queue.put((command, subprocess.command_id, data))
        ret = subprocess.command_id
        subprocess.command_id += 1
        return ret

    @staticmethod
    async def wait_subprocess_response(
        subprocess: Subprocess, command_id: int
    ) -> Tuple[SubprocessCommandType, Any]:
        while True:
            if command_id in subprocess.responses:
                return subprocess.responses.pop(command_id)

            try:
                response = subprocess.in_queue.get_nowait()
                if response[1] == command_id:
                    return response[0], response[2]
                else:
                    subprocess.responses[response[1]] = (
                        response[0],
                        response[2],
                    )
            except queue.Empty:
                await asyncio.sleep(0.1)

    async def run_detector_callback(self, callback_id: str) -> List[CommandAbc]:
        command_id = self.send_subprocess_command(
            self.__detectors_subprocess,
            SubprocessCommandType.RUN_DETECTOR_CALLBACK,
            callback_id,
        )

        command, data = await self.wait_subprocess_response(
            self.__detectors_subprocess, command_id
        )
        if command == SubprocessCommandType.DETECTOR_CALLBACK_SUCCESS:
            return data
        elif command == SubprocessCommandType.DETECTOR_CALLBACK_FAILURE:
            raise LspError(ErrorCodes.RequestFailed, data)
        else:
            raise LspError(
                ErrorCodes.InternalError, "Unexpected response from subprocess"
            )

    async def run_printer_callback(self, callback_id: str) -> List[CommandAbc]:
        command_id = self.send_subprocess_command(
            self.__printers_subprocess,
            SubprocessCommandType.RUN_PRINTER_CALLBACK,
            callback_id,
        )

        command, data = await self.wait_subprocess_response(
            self.__printers_subprocess, command_id
        )
        if command == SubprocessCommandType.PRINTER_CALLBACK_SUCCESS:
            return data
        elif command == SubprocessCommandType.PRINTER_CALLBACK_FAILURE:
            raise LspError(ErrorCodes.RequestFailed, data)
        else:
            raise LspError(
                ErrorCodes.InternalError,
                f"Unexpected response from subprocess: {command}",
            )

    def get_detector_code_lenses(
        self, path: Path
    ) -> Dict[Tuple[int, int], Set[CodeLensOptions]]:
        return self.__detector_code_lenses.get(path, {})

    def get_printer_code_lenses(
        self, path: Path
    ) -> Dict[Tuple[int, int], Set[CodeLensOptions]]:
        return self.__printer_code_lenses.get(path, {})

    def get_detector_hovers(
        self,
        path: Path,
        byte_offset: int,
        nested_most_node_offsets: Tuple[int, int],
    ) -> Set[HoverOptions]:
        ret = set()
        for (start, end), hovers in self.__detector_hovers.get(path, {}).items():
            for hover in hovers:
                if not (start <= byte_offset <= end):
                    continue
                if (
                    hover.on_child
                    or nested_most_node_offsets[0] == start
                    and nested_most_node_offsets[1] == end
                ):
                    ret.add(hover)
        return ret

    def get_printer_hovers(
        self,
        path: Path,
        byte_offset: int,
        nested_most_node_offsets: Tuple[int, int],
    ) -> Set[HoverOptions]:
        ret = set()
        for (start, end), hovers in self.__printer_hovers.get(path, {}).items():
            for hover in hovers:
                if not (start <= byte_offset <= end):
                    continue
                if (
                    hover.on_child
                    or nested_most_node_offsets[0] == start
                    and nested_most_node_offsets[1] == end
                ):
                    ret.add(hover)
        return ret

    def get_detector_inlay_hints(
        self, path: Path, byte_offsets: Tuple[int, int]
    ) -> Dict[int, Set[InlayHintOptions]]:
        ret = defaultdict(set)
        for offset, hints in self.__detector_inlay_hints.get(path, {}).items():
            if byte_offsets[0] <= offset <= byte_offsets[1]:
                ret[offset].update(hints)
        return ret

    def get_printer_inlay_hints(
        self, path: Path, byte_offsets: Tuple[int, int]
    ) -> Dict[int, Set[InlayHintOptions]]:
        ret = defaultdict(set)
        for offset, hints in self.__printer_inlay_hints.get(path, {}).items():
            if byte_offsets[0] <= offset <= byte_offsets[1]:
                ret[offset].update(hints)
        return ret

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
    def last_build(self) -> ProjectBuild:
        # TODO may be subject to race conditions

        import_graph_paths = {
            path
            for n, path in self.__last_graph.nodes(
                data="path"  # pyright: ignore reportGeneralTypeIssues
            )
        }

        # filter out only files that are not excluded from compilation
        return ProjectBuild(
            {
                p: tree
                for p, tree in self.__interval_trees.items()
                if p in import_graph_paths
            },
            self.__ir_reference_resolver,
            {p: su for p, su in self.__source_units.items() if p in import_graph_paths},
        )

    @property
    def last_build_info(self) -> ProjectBuildInfo:
        # TODO config may be subject to race conditions
        return ProjectBuildInfo(
            compilation_units={
                cu_hash.hex(): CompilationUnitBuildInfo(errors=list(errors))
                for cu_hash, errors in self.__latest_errors_per_cu.items()
            },
            source_units_info={
                node: SourceUnitInfo(
                    fs_path=self.__last_graph.nodes[node]["path"],
                    blake2b_hash=self.__last_graph.nodes[node]["hash"],
                )
                for node in self.__last_graph
            },
            allow_paths=self.__config.compiler.solc.allow_paths,
            exclude_paths=self.__config.compiler.solc.exclude_paths,
            include_paths=self.__config.compiler.solc.include_paths,
            settings=self.__last_build_settings,
            target_solidity_version=self.__config.compiler.solc.target_version,
            wake_version=self.__wake_version,
            incremental=True,
        )

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

    async def update_config(
        self, new_config: Dict, removed_options: Set, local_config_path: Path
    ):
        await self.__file_changes_queue.put(
            ConfigUpdate(new_config, removed_options, local_config_path)
        )

    async def force_recompile(self) -> None:
        self.__output_ready.clear()
        await self.__file_changes_queue.put(CustomFileChangeCommand.FORCE_RECOMPILE)

    async def force_rerun_detectors(self) -> None:
        await self.__file_changes_queue.put(
            CustomFileChangeCommand.FORCE_RERUN_DETECTORS
        )

    async def force_rerun_printers(self) -> None:
        await self.__file_changes_queue.put(
            CustomFileChangeCommand.FORCE_RERUN_PRINTERS
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

    async def __refresh_code_lenses(self) -> None:
        try:
            await self.__server.send_request(
                RequestMethodEnum.WORKSPACE_CODE_LENS_REFRESH, None
            )
        except LspError:
            pass

    async def _handle_change(
        self,
        change: Union[
            DidOpenTextDocumentParams,
            DidCloseTextDocumentParams,
            DidChangeTextDocumentParams,
            CustomFileChangeCommand,
            ConfigUpdate,
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
                        if not self.__file_excluded(file) and file.is_file():
                            self.__discovered_files.add(file.resolve())

                for file in self.__opened_files.keys():
                    if not self.__file_excluded(file):
                        self.__discovered_files.add(file)

                self.__force_compile_files.update(self.__discovered_files)
            elif change == CustomFileChangeCommand.FORCE_RERUN_DETECTORS:
                self.__force_run_detectors = True
            elif change == CustomFileChangeCommand.FORCE_RERUN_PRINTERS:
                self.__force_run_printers = True
        elif isinstance(change, ConfigUpdate):
            self.__config.local_config_path = change.local_config_path
            self.__config.set(change.new_config, change.removed_options)

            self.send_subprocess_command(
                self.__detectors_subprocess, SubprocessCommandType.CONFIG, self.__config
            )
            self.send_subprocess_command(
                self.__printers_subprocess, SubprocessCommandType.CONFIG, self.__config
            )
        elif isinstance(change, CreateFilesParams):
            for file in change.files:
                path = uri_to_path(file.uri)
                if (
                    path not in self.__discovered_files
                    and not self.__file_excluded(path)
                    and path.suffix == ".sol"
                ):
                    self.__discovered_files.add(path)
                    self.__force_compile_files.add(path)
        elif isinstance(change, RenameFilesParams):
            for rename in change.files:
                old_path = uri_to_path(rename.old_uri)
                self.__deleted_files.add(old_path)
                self.__discovered_files.discard(old_path)
                self.__opened_files.pop(old_path, None)

                new_path = uri_to_path(rename.new_uri)
                if (
                    new_path not in self.__discovered_files
                    and not self.__file_excluded(new_path)
                    and new_path.suffix == ".sol"
                ):
                    self.__discovered_files.add(new_path)
                    self.__force_compile_files.add(new_path)
        elif isinstance(change, DeleteFilesParams):
            for delete in change.files:
                path = uri_to_path(delete.uri)
                self.__deleted_files.add(path)
                self.__discovered_files.discard(path)
                self.__opened_files.pop(path, None)
        elif isinstance(change, DidOpenTextDocumentParams):
            path = uri_to_path(change.text_document.uri).resolve()
            self.__opened_files[path] = VersionedFile(
                change.text_document.text, change.text_document.version
            )
            if (
                path not in self.__discovered_files
                and not self.__file_excluded(path)
                and path.suffix == ".sol"
            ):
                self.__discovered_files.add(path)
                self.__force_compile_files.add(path)
            elif change.text_document.text != self.get_compiled_file(path).text:
                self.__force_compile_files.add(path)

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
        errors_per_cu: Optional[Dict[bytes, Set[SolcOutputError]]] = None,
    ) -> None:
        if errors_per_cu is None:
            errors_per_cu = {}

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
            self.__ir_reference_resolver.clear_all_indexed_nodes()
            self.__last_graph = nx.DiGraph()
            self.__latest_errors_per_cu = {}
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
            self.__ir_reference_resolver.clear_all_indexed_nodes()
            self.__last_graph = nx.DiGraph()
            self.__latest_errors_per_cu = {}
            return

        try:
            modified_files = {
                path: info.text.encode("utf-8")
                for path, info in self.__opened_files.items()
            }
            for p in self.__output_contents:
                if p not in modified_files:
                    modified_files[p] = self.__output_contents[p].text.encode("utf-8")

            if full_compile:
                graph, source_units_to_paths = self.__compiler.build_graph(
                    self.__discovered_files,
                    modified_files,
                    True,
                )

                # add to deleted files previously compiled files that are now excluded from build
                # will trigger post-destroy callbacks and remove them from source units
                for p in self.__source_units:
                    # use graph.nodes - i.e. discovered files + their dependencies from exclude paths
                    if p not in source_units_to_paths.values():
                        self.__deleted_files.add(p)
                self.__last_graph = graph
            else:
                graph, _ = self.__compiler.build_graph(
                    files_to_compile,
                    modified_files,
                    True,
                )

            for source_unit_name in graph.nodes:
                path = graph.nodes[source_unit_name]["path"]
                content = graph.nodes[source_unit_name]["content"]
                if (
                    path not in self.__opened_files
                    and path not in self.__output_contents
                ):
                    self.__output_contents[path] = VersionedFile(
                        content.decode(encoding="utf-8"), None
                    )

        except CompilationError as e:
            await self.__server.log_message(str(e), MessageType.ERROR)
            for file in self.__discovered_files:
                # clear diagnostics
                await self.__diagnostic_queue.put((file, set()))
            self.__interval_trees.clear()
            self.__source_units.clear()
            self.__ir_reference_resolver.clear_all_indexed_nodes()
            self.__last_graph = nx.DiGraph()
            self.__latest_errors_per_cu = {}
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
        if full_compile:
            self.__last_build_settings = build_settings

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
                            graph.subgraph(
                                source_unit_names
                            ).copy(),  # pyright: ignore reportArgumentType
                            versions,
                        )
                    )
                    source_unit_names = set(cu.source_unit_names)
                    versions = cu.versions

            merged_compilation_units.append(
                CompilationUnit(
                    graph.subgraph(
                        source_unit_names
                    ).copy(),  # pyright: ignore reportArgumentType
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
                if file in self.__interval_trees:
                    self.__interval_trees.pop(file)
                if file in self.__source_units:
                    self.__ir_reference_resolver.run_destroy_callbacks(file)
                    self.__source_units.pop(file)
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
            self.__ir_reference_resolver.clear_all_indexed_nodes()
            self.__last_graph = nx.DiGraph()
            self.__latest_errors_per_cu = {}
            return

        errors_without_location: Set[SolcOutputError] = set()
        errors_per_file: Dict[Path, Set[Diagnostic]] = deepcopy(
            self.__compilation_errors
        )

        for cu, solc_output in zip(compilation_units, ret):
            errors_per_cu[cu.hash] = set(solc_output.errors)
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
            self.__ir_reference_resolver.clear_all_indexed_nodes()
            self.__latest_errors_per_cu = errors_per_cu
            return

        # files passed as files_to_compile and files importing them
        files_to_recompile = set(
            graph.nodes[n[1]]["path"]  # pyright: ignore reportGeneralTypeIssues
            for n in nx.edge_bfs(
                graph,
                [
                    source_unit_name
                    for source_unit_name in graph.nodes  # pyright: ignore reportGeneralTypeIssues
                    if graph.nodes[  # pyright: ignore reportGeneralTypeIssues
                        source_unit_name
                    ][  # pyright: ignore reportGeneralTypeIssues
                        "path"
                    ]
                    in files_to_compile  # pyright: ignore reportGeneralTypeIssues
                ],
            )
        ) | set(files_to_compile)

        # clear indexed node types responsible for handling multiple structurally different ASTs for the same file
        self.__ir_reference_resolver.clear_indexed_nodes(files_to_recompile)

        for deleted_file in self.__deleted_files:
            await self.__diagnostic_queue.put((deleted_file, []))
            if deleted_file in self.__source_units:
                self.__ir_reference_resolver.run_destroy_callbacks(deleted_file)
                self.__source_units.pop(deleted_file)

        successful_compilation_units = []
        for cu, solc_output in zip(compilation_units, ret):
            for file in cu.files:
                if file in self.__line_indexes:
                    self.__line_indexes.pop(file)
                if file in self.__opened_files:
                    self.__output_contents[file] = self.__opened_files[file]

            errored_files: Set[Path] = set()

            for error in solc_output.errors:
                if error.source_location is not None:
                    path = cu.source_unit_name_to_path(error.source_location.file)

                    if (
                        error.source_location.start >= 0
                        and error.source_location.end >= 0
                    ):
                        start_line = self.get_line_pos_from_byte_offset(
                            path, error.source_location.start
                        )[0]
                        end_line = self.get_line_pos_from_byte_offset(
                            path, error.source_location.end
                        )[0]
                    else:
                        start_line = 0
                        end_line = 0

                    ignored = (
                        error.severity != SolcOutputErrorSeverityEnum.ERROR
                        and error_commented_out(
                            error.error_code,
                            start_line,
                            end_line,
                            self.__last_graph.nodes[  # pyright: ignore reportGeneralTypeIssues
                                error.source_location.file
                            ][
                                "wake_comments"
                            ],
                        )
                    )
                    if not ignored or self.__ignored_detections_supported:
                        errors_per_file[path].add(
                            self.__solc_error_to_diagnostic(error, path, cu, ignored)
                        )
                    if error.severity == SolcOutputErrorSeverityEnum.ERROR:
                        errored_files.add(path)
                else:
                    # whole compilation unit errored
                    if error.severity == SolcOutputErrorSeverityEnum.ERROR:
                        errored_files.update(cu.files)

            _out_edge_bfs(cu, errored_files, errored_files)

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
                successful_compilation_units.append((cu, solc_output))

        # destroy callbacks for IR nodes that will be replaced by new ones must be executed before
        # new IR nodes are created
        callback_processed_files: Set[Path] = set()
        for cu, solc_output in successful_compilation_units:
            # files requested to be compiled and files that import these files (even indirectly)
            recompiled_files: Set[Path] = set()
            _out_edge_bfs(cu, files_to_compile & cu.files, recompiled_files)

            # run destroy callbacks for files that were recompiled and their IR nodes will be replaced
            for source_unit_name in solc_output.sources.keys():
                path = cu.source_unit_name_to_path(source_unit_name)
                if (
                    path in self.__source_units and path not in recompiled_files
                ) or path in callback_processed_files:
                    continue
                callback_processed_files.add(path)
                self.__ir_reference_resolver.run_destroy_callbacks(path)

        processed_files: Set[Path] = set()
        for cu_index, (cu, solc_output) in enumerate(successful_compilation_units):
            # files requested to be compiled and files that import these files (even indirectly)
            recompiled_files: Set[Path] = set()
            _out_edge_bfs(cu, files_to_compile & cu.files, recompiled_files)

            for source_unit_name, raw_ast in solc_output.sources.items():
                path: Path = cu.source_unit_name_to_path(source_unit_name)
                ast = AstSolc.model_validate(raw_ast.ast)

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
                self.__source_units[path] = SourceUnit(init, ast)
                self.__interval_trees[path] = interval_tree

                self.__last_compilation_source_units[path] = self.__source_units[path]
                self.__last_compilation_interval_trees[path] = self.__interval_trees[
                    path
                ]

                if path in self.__opened_files:
                    self.__last_successful_compilation_contents[
                        path
                    ] = self.__opened_files[path]
                else:
                    self.__last_successful_compilation_contents[path] = VersionedFile(
                        cu.graph.nodes[  # pyright: ignore reportGeneralTypeIssues
                            source_unit_name
                        ]["content"],
                        None,
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

        # send compiler warnings and errors first without waiting for detectors to finish
        for path, errors in errors_per_file.items():
            await self.__diagnostic_queue.put((path, errors))

        if len(files_to_recompile) > 0:
            # avoid infinite recursion
            if files_to_recompile != files_to_compile or full_compile:
                await self.__compile(files_to_recompile, False, errors_per_cu)

        if full_compile:
            self.__latest_errors_per_cu = errors_per_cu

    async def __run_detectors_task(self) -> None:
        if self.__detectors_task is not None:
            self.__detectors_task.cancel()

            try:
                await self.__detectors_task
            except asyncio.CancelledError:
                pass

        if self.__config.lsp.detectors.enable:
            self.__detectors_task = self.__server.create_task(self.__run_detectors())

    async def __run_printers_task(self) -> None:
        if self.__printers_task is not None:
            self.__printers_task.cancel()

            try:
                await self.__printers_task
            except asyncio.CancelledError:
                pass

        self.__printers_task = self.__server.create_task(self.__run_printers())

    async def __run_printers(self) -> None:
        progress_token = await self.__server.progress_begin("Running printers")

        try:
            command_id = self.send_subprocess_command(
                self.__printers_subprocess, SubprocessCommandType.RUN_PRINTERS, None
            )

            command, data = await self.wait_subprocess_response(
                self.__printers_subprocess, command_id
            )
            if command == SubprocessCommandType.PRINTERS_SUCCESS:
                (
                    failed_plugin_entry_points,
                    failed_plugin_paths,
                    exceptions,
                    logging_buffer,
                    commands,
                    self.__printer_code_lenses,
                    self.__printer_hovers,
                    self.__printer_inlay_hints,
                ) = data

                for package, e in failed_plugin_entry_points:
                    await self.__server.show_message(
                        f"Failed to load printers from plugin module {package}: {e}",
                        MessageType.ERROR,
                    )
                    await self.__server.log_message(
                        f"Failed to load printers from plugin module {package}: {e}",
                        MessageType.ERROR,
                    )

                for path, e in failed_plugin_paths:
                    await self.__server.show_message(
                        f"Failed to load printers from path {path}: {e}",
                        MessageType.ERROR,
                    )
                    await self.__server.log_message(
                        f"Failed to load printers from path {path}: {e}",
                        MessageType.ERROR,
                    )

                for log, log_type in logging_buffer:
                    await self.__server.log_message(log, log_type)

                for printer_name, exception_str in exceptions.items():
                    await self.__server.show_message(
                        f"Exception while running printer {printer_name}: {exception_str}",
                        MessageType.ERROR,
                    )
                    await self.__server.log_message(
                        f"Exception while running printer {printer_name}: {exception_str}",
                        MessageType.ERROR,
                    )

                if len(commands) > 0:
                    await self.__server.send_notification(
                        "wake/executeCommands", list(commands)
                    )
            elif command == SubprocessCommandType.PRINTERS_FAILURE:
                self.__printer_code_lenses = {}
                self.__printer_hovers = {}
                self.__printer_inlay_hints = {}

                await self.__server.show_message(
                    f"Exception occurred while running printers:\n{data}",
                    MessageType.ERROR,
                )
                await self.__server.log_message(
                    f"Exception occurred while running printers:\n{data}",
                    MessageType.ERROR,
                )
            elif command == SubprocessCommandType.PRINTERS_CANCELLED:
                return
            else:
                await self.__server.show_message(
                    f"Unexpected response from subprocess: {command}", MessageType.ERROR
                )
                await self.__server.log_message(
                    f"Unexpected response from subprocess: {command}", MessageType.ERROR
                )
        finally:
            if progress_token is not None:
                await self.__server.progress_end(progress_token)

        # make sure that code lenses are refreshed
        await self.__refresh_code_lenses()

        # make sure that inline values are refreshed
        try:
            await self.__server.send_request(RequestMethodEnum.INLAY_HINT_REFRESH, None)
        except LspError:
            pass

    async def __run_detectors(self) -> None:
        progress_token = await self.__server.progress_begin("Running detectors")

        try:
            command_id = self.send_subprocess_command(
                self.__detectors_subprocess, SubprocessCommandType.RUN_DETECTORS, None
            )

            command, data = await self.wait_subprocess_response(
                self.__detectors_subprocess, command_id
            )
            if command == SubprocessCommandType.DETECTORS_SUCCESS:
                (
                    failed_plugin_entry_points,
                    failed_plugin_paths,
                    errors_per_file,
                    exceptions,
                    logging_buffer,
                    commands,
                    self.__detector_code_lenses,
                    self.__detector_hovers,
                    self.__detector_inlay_hints,
                ) = data

                for package, e in failed_plugin_entry_points:
                    await self.__server.show_message(
                        f"Failed to load detectors from plugin module {package}: {e}",
                        MessageType.ERROR,
                    )
                    await self.__server.log_message(
                        f"Failed to load detectors from plugin module {package}: {e}",
                        MessageType.ERROR,
                    )

                for path, e in failed_plugin_paths:
                    await self.__server.show_message(
                        f"Failed to load detectors from path {path}: {e}",
                        MessageType.ERROR,
                    )
                    await self.__server.log_message(
                        f"Failed to load detectors from path {path}: {e}",
                        MessageType.ERROR,
                    )

                for log, log_type in logging_buffer:
                    await self.__server.log_message(log, log_type)

                # merge compilation errors and detector errors
                for path, errors in self.__compilation_errors.items():
                    if path in errors_per_file:
                        errors_per_file[path].update(errors)
                    else:
                        errors_per_file[path] = errors

                # send both compiler and detector warnings and errors
                for path, errors in errors_per_file.items():
                    await self.__diagnostic_queue.put((path, errors))

                for detector_name, exception_str in exceptions.items():
                    await self.__server.show_message(
                        f"Exception while running detector {detector_name}: {exception_str}",
                        MessageType.ERROR,
                    )
                    await self.__server.log_message(
                        f"Exception while running detector {detector_name}: {exception_str}",
                        MessageType.ERROR,
                    )

                if len(commands) > 0:
                    await self.__server.send_notification(
                        "wake/executeCommands", list(commands)
                    )
            elif command == SubprocessCommandType.DETECTORS_FAILURE:
                await self.__server.show_message(
                    f"Exception occurred while running detectors:\n{data}",
                    MessageType.ERROR,
                )
                await self.__server.log_message(
                    f"Exception occurred while running detectors:\n{data}",
                    MessageType.ERROR,
                )
            elif command == SubprocessCommandType.DETECTORS_CANCELLED:
                return
            else:
                await self.__server.show_message(
                    f"Unexpected response from subprocess: {command}", MessageType.ERROR
                )
                await self.__server.log_message(
                    f"Unexpected response from subprocess: {command}", MessageType.ERROR
                )
        finally:
            if progress_token is not None:
                await self.__server.progress_end(progress_token)

        # make sure that code lenses are refreshed
        await self.__refresh_code_lenses()

        # make sure that inline values are refreshed
        try:
            await self.__server.send_request(RequestMethodEnum.INLAY_HINT_REFRESH, None)
        except LspError:
            pass

    async def __compilation_loop(self):
        if self.__perform_files_discovery:
            # perform Solidity files discovery
            for file in self.__config.project_root_path.rglob("**/*.sol"):
                if not self.__file_excluded(file) and file.is_file():
                    self.__discovered_files.add(file.resolve())

            # perform initial compilation
            await self.__compile(self.__discovered_files)
            await self.__refresh_code_lenses()

            self.send_subprocess_command(
                self.__printers_subprocess,
                SubprocessCommandType.BUILD,
                (self.last_build, self.last_build_info, self.last_graph),
            )
            await self.__run_printers_task()
            self.send_subprocess_command(
                self.__detectors_subprocess,
                SubprocessCommandType.BUILD,
                (self.last_build, self.last_build_info, self.last_graph),
            )
            await self.__run_detectors_task()

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
                self.__detector_code_lenses.clear()
                self.__printer_code_lenses.clear()
                self.__detector_hovers.clear()
                self.__printer_hovers.clear()
                self.__detector_inlay_hints.clear()
                self.__printer_inlay_hints.clear()
                await self.__refresh_code_lenses()

                await self.__compile(
                    self.__force_compile_files.union(self.__modified_files)
                )

                self.__force_run_detectors = True
                self.__force_run_printers = True
                self.__force_compile_files.clear()
                self.__modified_files.clear()
                self.__deleted_files.clear()

            if self.__file_changes_queue.empty():
                self.output_ready.set()

                if self.__force_run_printers:
                    self.send_subprocess_command(
                        self.__printers_subprocess,
                        SubprocessCommandType.BUILD,
                        (self.last_build, self.last_build_info, self.last_graph),
                    )
                    await self.__run_printers_task()
                if self.__force_run_detectors:
                    self.send_subprocess_command(
                        self.__detectors_subprocess,
                        SubprocessCommandType.BUILD,
                        (self.last_build, self.last_build_info, self.last_graph),
                    )
                    await self.__run_detectors_task()

                self.__force_run_detectors = False
                self.__force_run_printers = False

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
        self, error: SolcOutputError, path: Path, cu: CompilationUnit, ignored: bool
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

        diag = Diagnostic(
            range=range_,
            severity=severity,
            code=error.error_code,
            source="Wake(solc)",
            message=error.message,
            data=CompilationErrorAdditionalInfo(
                severity=error.severity,
                ignored=ignored,
                source_unit_name=error.source_location.file,
            ),
        )
        if (
            error.secondary_source_locations is not None
            and len(error.secondary_source_locations) > 0
        ):
            related_info = []
            for secondary_source_location in error.secondary_source_locations:
                if (
                    secondary_source_location.file is None
                    or secondary_source_location.start is None
                    or secondary_source_location.end is None
                ):
                    continue

                if (
                    secondary_source_location.start >= 0
                    and secondary_source_location.end >= 0
                ):
                    range_ = self.get_range_from_byte_offsets(
                        cu.source_unit_name_to_path(secondary_source_location.file),
                        (
                            secondary_source_location.start,
                            secondary_source_location.end,
                        ),
                    )
                else:
                    range_ = Range(
                        start=Position(line=0, character=0),
                        end=Position(line=0, character=0),
                    )

                related_info.append(
                    DiagnosticRelatedInformation(
                        location=Location(
                            uri=DocumentUri(
                                path_to_uri(
                                    cu.source_unit_name_to_path(
                                        secondary_source_location.file
                                    )
                                )
                            ),
                            range=range_,
                        ),
                        message=secondary_source_location.message,
                    )
                )
            diag.related_information = related_info
        return diag

    def __file_excluded(self, path: Path) -> bool:
        return any(
            is_relative_to(path, p) for p in self.__config.compiler.solc.exclude_paths
        )
