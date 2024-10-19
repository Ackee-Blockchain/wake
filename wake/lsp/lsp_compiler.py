from __future__ import annotations

import asyncio
import difflib
import glob
import multiprocessing
import multiprocessing.connection
import pickle
import queue
import re
import threading
import time
import weakref
from collections import Counter, defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
from itertools import chain
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
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

import wake.lsp.callback_commands as callback_commands
from wake.compiler.exceptions import CompilationError
from wake.lsp.logging_handler import LspLoggingHandler

from ..analysis.utils import get_all_base_and_child_declarations
from ..compiler.build_data_model import (
    CompilationUnitBuildInfo,
    ProjectBuild,
    ProjectBuildInfo,
    SourceUnitInfo,
)
from ..core.solidity_version import (
    SolidityVersion,
    SolidityVersionRange,
    SolidityVersionRanges,
)
from ..core.wake_comments import error_commented_out
from ..ir.enums import GlobalSymbol
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
from .utils.position import changes_to_byte_offset

if TYPE_CHECKING:
    from .server import LspServer

import networkx as nx
from intervaltree import IntervalTree

from wake.compiler import SolcOutput, SolcOutputContractInfo, SolcOutputSelectionEnum
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
    CommandType,
    CopyToClipboardCommand,
    GoToLocationsCommand,
    HoverOptions,
    InlayHintOptions,
    OpenCommand,
    PeekLocationsCommand,
    ShowDotCommand,
    ShowMessageCommand,
)
from wake.ir import (
    BinaryOperation,
    DeclarationAbc,
    FunctionDefinition,
    Identifier,
    IdentifierPath,
    IdentifierPathPart,
    MemberAccess,
    ModifierDefinition,
    SourceUnit,
    UnaryOperation,
    UserDefinedTypeName,
    VariableDeclaration,
    YulIdentifier,
)
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
    FileChangeType,
    FileEvent,
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
class BytecodeCompileResult:
    abi: List
    bytecode: str


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
    __disk_changed_files: Set[Path]
    early_opened_files: Dict[
        Path, VersionedFile
    ]  # opened files contents as soon as they arrive
    __early_disk_contents: Dict[Path, bytes]
    __opened_files: Dict[Path, VersionedFile]
    __modified_files: Set[Path]
    __force_compile_files: Set[Path]
    __compiler: SolidityCompiler
    __output_contents: Dict[Path, VersionedFile]
    __compilation_errors: Dict[Path, Set[Diagnostic]]
    __last_successful_compilation_contents: Dict[Path, Dict[Path, bytes]]
    __detector_contents: Dict[Path, bytes]
    __printer_contents: Dict[Path, bytes]
    __interval_trees: Dict[Path, IntervalTree]
    __source_units: Dict[Path, SourceUnit]
    __last_compilation_interval_trees: Dict[Path, IntervalTree]
    __last_compilation_source_units: Dict[Path, SourceUnit]
    __last_graph: nx.DiGraph
    __last_build_settings: Dict[Optional[str], SolcInputSettings]
    __line_indexes: Dict[Path, List[Tuple[bytes, int]]]
    __early_line_indexes: Dict[Path, List[Tuple[bytes, int]]]
    __perform_files_discovery: bool
    __force_run_detectors: bool
    __force_run_printers: bool
    __wake_version: str
    __latest_errors_per_cu: Dict[bytes, Set[SolcOutputError]]
    __ignored_detections_supported: bool
    __cu_counter: Counter[
        bytes
    ]  # how many source units of each cu hash are still present in self.__source_units

    __ir_reference_resolver: ReferenceResolver

    __compilation_ready: asyncio.Event
    __cache_ready: asyncio.Event

    __detectors_subprocess: Subprocess
    __printers_subprocess: Subprocess

    __detectors_task: Optional[asyncio.Task]
    __printers_task: Optional[asyncio.Task]

    go_to_definition_cache: weakref.WeakKeyDictionary[
        Union[
            Identifier,
            MemberAccess,
            IdentifierPathPart,
            YulIdentifier,
            UnaryOperation,
            BinaryOperation,
        ],
        Dict[Path, Set[Tuple[int, int]]],
    ]
    hover_cache: weakref.WeakKeyDictionary[
        Union[
            Identifier,
            MemberAccess,
            IdentifierPathPart,
            YulIdentifier,
            UnaryOperation,
            BinaryOperation,
        ],
        str,
    ]
    go_to_type_definition_cache: weakref.WeakKeyDictionary[
        Union[
            Identifier,
            MemberAccess,
            IdentifierPathPart,
            YulIdentifier,
            VariableDeclaration,
        ],
        Tuple[Path, int, int],
    ]

    def __init__(
        self,
        server: LspServer,
        diagnostic_queue: asyncio.Queue,
        perform_files_discovery: bool,
    ):
        self.__server = weakref.proxy(server)
        self.__file_changes_queue = asyncio.Queue()
        self.__diagnostic_queue = diagnostic_queue
        self.__stop_event = threading.Event()
        self.__discovered_files = set()
        self.__deleted_files = set()
        self.__disk_changed_files = set()
        self.early_opened_files = {}
        self.__early_disk_contents = {}
        self.__opened_files = {}
        self.__modified_files = set()
        self.__force_compile_files = set()
        self.__interval_trees = {}
        self.__source_units = {}
        self.__last_compilation_interval_trees = {}
        self.__last_compilation_source_units = {}
        self.__last_graph = nx.DiGraph()
        self.__last_build_settings = {}
        self.__line_indexes = {}
        self.__early_line_indexes = {}
        self.__output_contents = dict()
        self.__compilation_errors = dict()
        self.__last_successful_compilation_contents = dict()
        self.__detector_contents = dict()
        self.__printer_contents = dict()
        self.__compilation_ready = asyncio.Event()
        self.__cache_ready = asyncio.Event()
        self.__perform_files_discovery = perform_files_discovery
        self.__force_run_detectors = False
        self.__force_run_printers = False
        self.__wake_version = get_package_version("eth-wake")
        self.__latest_errors_per_cu = {}
        self.__cu_counter = Counter()
        self.go_to_definition_cache = weakref.WeakKeyDictionary()
        self.hover_cache = weakref.WeakKeyDictionary()
        self.go_to_type_definition_cache = weakref.WeakKeyDictionary()

        try:
            if server.tfs_version is not None and packaging.version.parse(
                server.tfs_version
            ) > packaging.version.parse("1.10.3"):
                self.__ignored_detections_supported = True
            else:
                self.__ignored_detections_supported = False
        except packaging.version.InvalidVersion:
            self.__ignored_detections_supported = False

        self.__ir_reference_resolver = ReferenceResolver(lsp=True)
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

    async def wait_subprocess_response(
        self, subprocess: Subprocess, command_id: int
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

            if subprocess.process is not None and not subprocess.process.is_alive():
                while not subprocess.in_queue.empty():
                    response = subprocess.in_queue.get_nowait()
                    subprocess.responses[response[1]] = (
                        response[0],
                        response[2],
                    )

                for command_type, data in subprocess.responses.values():
                    if command_type == SubprocessCommandType.DETECTORS_FAILURE:
                        await self.__server.log_message(f"Detectors error: {data}", MessageType.ERROR)
                    elif command_type == SubprocessCommandType.PRINTERS_FAILURE:
                        await self.__server.log_message(f"Printers error: {data}", MessageType.ERROR)

                raise RuntimeError("Subprocess has terminated unexpectedly")

    def __process_commands(
        self,
        commands: List[CommandType],
        get_forward_changes: Callable[[Path], Optional[IntervalTree]],
    ) -> List[callback_commands.CommandAbc]:
        ret = []
        for command in commands:
            if isinstance(command, (GoToLocationsCommand, PeekLocationsCommand)):
                forward_changes = get_forward_changes(command.path)
                if (
                    forward_changes is None
                    or len(forward_changes[command.byte_offset]) > 0
                ):
                    continue

                line, col = self.get_early_line_pos_from_byte_offset(
                    command.path,
                    changes_to_byte_offset(forward_changes[0 : command.byte_offset])
                    + command.byte_offset,
                )

                locations = []
                for path, start, end in command.locations:
                    forward_changes = get_forward_changes(path)
                    if forward_changes is None or len(forward_changes[start:end]) > 0:
                        continue

                    new_start = changes_to_byte_offset(forward_changes[0:start]) + start
                    new_end = changes_to_byte_offset(forward_changes[0:end]) + end

                    locations.append(
                        Location(
                            uri=path_to_uri(path),
                            range=self.get_early_range_from_byte_offsets(
                                path, (new_start, new_end)
                            ),
                        )
                    )

                if isinstance(command, GoToLocationsCommand):
                    ret.append(
                        callback_commands.GoToLocationsCommand(
                            uri=path_to_uri(command.path),
                            position=Position(line=line, character=col),
                            locations=locations,
                            multiple=command.multiple,
                            no_results_message=command.no_results_message,
                        )
                    )
                else:
                    ret.append(
                        callback_commands.PeekLocationsCommand(
                            uri=path_to_uri(command.path),
                            position=Position(line=line, character=col),
                            locations=locations,
                            multiple=command.multiple,
                        )
                    )
            elif isinstance(command, OpenCommand):
                ret.append(callback_commands.OpenCommand(uri=DocumentUri(command.uri)))
            elif isinstance(command, CopyToClipboardCommand):
                ret.append(callback_commands.CopyToClipboardCommand(text=command.text))
            elif isinstance(command, ShowMessageCommand):
                ret.append(
                    callback_commands.ShowMessageCommand(
                        message=command.message, kind=command.kind
                    )
                )
            elif isinstance(command, ShowDotCommand):
                ret.append(
                    callback_commands.ShowDotCommand(
                        title=command.title, dot=command.dot
                    )
                )

        return ret

    async def run_detector_callback(
        self, callback_id: str
    ) -> List[callback_commands.CommandAbc]:
        command_id = self.send_subprocess_command(
            self.__detectors_subprocess,
            SubprocessCommandType.RUN_DETECTOR_CALLBACK,
            callback_id,
        )

        command, data = await self.wait_subprocess_response(
            self.__detectors_subprocess, command_id
        )
        if command == SubprocessCommandType.DETECTOR_CALLBACK_SUCCESS:
            return self.__process_commands(data, self.get_detector_forward_changes)
        elif command == SubprocessCommandType.DETECTOR_CALLBACK_FAILURE:
            raise LspError(ErrorCodes.RequestFailed, data)
        else:
            raise LspError(
                ErrorCodes.InternalError, "Unexpected response from subprocess"
            )

    async def run_printer_callback(
        self, callback_id: str
    ) -> List[callback_commands.CommandAbc]:
        command_id = self.send_subprocess_command(
            self.__printers_subprocess,
            SubprocessCommandType.RUN_PRINTER_CALLBACK,
            callback_id,
        )

        command, data = await self.wait_subprocess_response(
            self.__printers_subprocess, command_id
        )
        if command == SubprocessCommandType.PRINTER_CALLBACK_SUCCESS:
            return self.__process_commands(data, self.get_printer_forward_changes)
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
    def compilation_ready(self) -> asyncio.Event:
        return self.__compilation_ready

    @property
    def cache_ready(self) -> asyncio.Event:
        return self.__cache_ready

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
        target_versions: Dict[Optional[str], Optional[SolidityVersion]] = {
            s: info.target_version for s, info in self.__config.subproject.items()
        }
        target_versions[None] = self.__config.compiler.solc.target_version

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
            target_solidity_versions=target_versions,
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
    def _compute_diff_interval_tree(self, a: bytes, b: bytes) -> IntervalTree:
        seq_matcher = difflib.SequenceMatcher(None, a, b)
        interval_tree = IntervalTree()
        for tag, i1, i2, j1, j2 in seq_matcher.get_opcodes():
            if tag == "equal":
                continue
            interval_tree.addi(i1, i2 + 1, (tag, j1, j2 + 1))
        return interval_tree

    def get_last_compilation_forward_changes(
        self, context_file: Path, file: Path
    ) -> Optional[IntervalTree]:
        """
        Returns diff changes of the content of `file` at the time of the last successful compilation of `context_file`
        compared to the current content of `file`.
        """
        if (
            context_file not in self.__last_successful_compilation_contents
            or file not in self.__last_successful_compilation_contents[context_file]
        ):
            return None

        if file in self.early_opened_files:
            current_content = self.early_opened_files[file].text.encode("utf-8")
        elif file in self.__early_disk_contents:
            current_content = self.__early_disk_contents[file]
        elif file.is_file():
            current_content = file.read_bytes()
        else:
            return None

        return self._compute_diff_interval_tree(
            self.__last_successful_compilation_contents[context_file][file],
            current_content,
        )

    def get_last_compilation_backward_changes(
        self, context_file: Path, file: Path
    ) -> Optional[IntervalTree]:
        """
        Returns diff changes of the current content of `file` compared to the content of `file` at the time of the last
        successful compilation of `context_file`.
        """
        if (
            context_file not in self.__last_successful_compilation_contents
            or file not in self.__last_successful_compilation_contents[context_file]
        ):
            return None

        if file in self.early_opened_files:
            current_content = self.early_opened_files[file].text.encode("utf-8")
        elif file in self.__early_disk_contents:
            current_content = self.__early_disk_contents[file]
        elif file.is_file():
            current_content = file.read_bytes()
        else:
            return None

        return self._compute_diff_interval_tree(
            current_content,
            self.__last_successful_compilation_contents[context_file][file],
        )

    def get_detector_forward_changes(self, file: Path) -> Optional[IntervalTree]:
        if file not in self.__detector_contents:
            return None

        if file in self.early_opened_files:
            current_content = self.early_opened_files[file].text.encode("utf-8")
        elif file in self.__early_disk_contents:
            current_content = self.__early_disk_contents[file]
        elif file.is_file():
            current_content = file.read_bytes()
        else:
            return None

        return self._compute_diff_interval_tree(
            self.__detector_contents[file],
            current_content,
        )

    def get_detector_backward_changes(self, file: Path) -> Optional[IntervalTree]:
        if file not in self.__detector_contents:
            return None

        if file in self.early_opened_files:
            current_content = self.early_opened_files[file].text.encode("utf-8")
        elif file in self.__early_disk_contents:
            current_content = self.__early_disk_contents[file]
        elif file.is_file():
            current_content = file.read_bytes()
        else:
            return None

        return self._compute_diff_interval_tree(
            current_content,
            self.__detector_contents[file],
        )

    def get_printer_forward_changes(self, file: Path) -> Optional[IntervalTree]:
        if file not in self.__printer_contents:
            return None

        if file in self.early_opened_files:
            current_content = self.early_opened_files[file].text.encode("utf-8")
        elif file in self.__early_disk_contents:
            current_content = self.__early_disk_contents[file]
        elif file.is_file():
            current_content = file.read_bytes()
        else:
            return None

        return self._compute_diff_interval_tree(
            self.__printer_contents[file],
            current_content,
        )

    def get_printer_backward_changes(self, file: Path) -> Optional[IntervalTree]:
        if file not in self.__printer_contents:
            return None

        if file in self.early_opened_files:
            current_content = self.early_opened_files[file].text.encode("utf-8")
        elif file in self.__early_disk_contents:
            current_content = self.__early_disk_contents[file]
        elif file.is_file():
            current_content = file.read_bytes()
        else:
            return None

        return self._compute_diff_interval_tree(
            current_content,
            self.__printer_contents[file],
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
            FileEvent,
        ],
    ) -> None:
        self.compilation_ready.clear()
        await self.__file_changes_queue.put(change)

        if isinstance(change, FileEvent):
            path = uri_to_path(change.uri).resolve()
            if change.type == FileChangeType.CREATED and path.is_file():
                self.__early_disk_contents[path] = path.read_bytes()
                self.__early_line_indexes.pop(path, None)
            elif change.type == FileChangeType.CHANGED and path.is_file():
                self.__early_disk_contents[path] = path.read_bytes()
                self.__early_line_indexes.pop(path, None)
            elif change.type == FileChangeType.DELETED:
                self.__early_disk_contents.pop(path, None)
                self.__early_line_indexes.pop(path, None)
        elif isinstance(change, DidOpenTextDocumentParams):
            path = uri_to_path(change.text_document.uri).resolve()
            self.early_opened_files[path] = VersionedFile(
                change.text_document.text, change.text_document.version
            )
            self.__early_disk_contents.pop(path, None)
        elif isinstance(change, DidCloseTextDocumentParams):
            path = uri_to_path(change.text_document.uri).resolve()
            self.early_opened_files.pop(path, None)
        elif isinstance(change, DidChangeTextDocumentParams):
            path = uri_to_path(change.text_document.uri).resolve()
            for content_change in change.content_changes:
                start = content_change.range.start
                end = content_change.range.end

                # str.splitlines() removes empty lines => cannot be used
                # str.split() removes separators => cannot be used
                tmp_lines = re.split(r"(\r?\n)", self.early_opened_files[path].text)
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

                try:
                    self.early_opened_files[path] = VersionedFile(
                        "".join(line.decode(ENCODING) for line in lines),
                        change.text_document.version,
                    )
                except UnicodeDecodeError:
                    pass

                self.__early_line_indexes.pop(path, None)
        elif isinstance(change, CreateFilesParams):
            for file in change.files:
                path = uri_to_path(file.uri).resolve()
                if path.is_file():
                    self.__early_disk_contents[path] = path.read_bytes()
                self.__early_line_indexes.pop(path, None)
        elif isinstance(change, RenameFilesParams):
            for rename in change.files:
                old_path = uri_to_path(rename.old_uri).resolve()
                new_path = uri_to_path(rename.new_uri).resolve()

                if old_path in self.__early_disk_contents:
                    self.__early_disk_contents[
                        new_path
                    ] = self.__early_disk_contents.pop(old_path)
                if old_path in self.__early_line_indexes:
                    self.__early_line_indexes[new_path] = self.__early_line_indexes.pop(
                        old_path
                    )
        elif isinstance(change, DeleteFilesParams):
            for file in change.files:
                path = uri_to_path(file.uri).resolve()
                self.__early_disk_contents.pop(path, None)
                self.__early_line_indexes.pop(path, None)

    async def update_config(
        self, new_config: Dict, removed_options: Set, local_config_path: Path
    ):
        await self.__file_changes_queue.put(
            ConfigUpdate(new_config, removed_options, local_config_path)
        )

    async def force_recompile(self) -> None:
        self.__compilation_ready.clear()
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
                file.read_text(encoding="utf-8"), None
            )
        return self.__output_contents[file]

    def get_line_pos_from_byte_offset(
        self, file: Path, byte_offset: int
    ) -> Tuple[int, int]:
        if file not in self.__line_indexes:
            self.__line_indexes[file] = self.__setup_line_index(
                self.get_compiled_file(file).text
            )

        encoded_lines = self.__line_indexes[file]
        line_num = _binary_search(encoded_lines, byte_offset)
        line_data, prefix_sum = encoded_lines[line_num]
        line_offset = byte_offset - prefix_sum
        return line_num, line_offset

    def get_early_line_pos_from_byte_offset(
        self, file: Path, byte_offset: int
    ) -> Tuple[int, int]:
        if file not in self.__early_line_indexes:
            self.__early_line_indexes[file] = self.__setup_line_index(
                self.early_opened_files[file].text
                if file in self.early_opened_files
                else file.read_text("utf-8")
            )

        encoded_lines = self.__early_line_indexes[file]
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

    def get_early_range_from_byte_offsets(
        self, file: Path, byte_offsets: Tuple[int, int]
    ) -> Range:
        start_line, start_column = self.get_early_line_pos_from_byte_offset(
            file, byte_offsets[0]
        )
        end_line, end_column = self.get_early_line_pos_from_byte_offset(
            file, byte_offsets[1]
        )

        return Range(
            start=Position(line=start_line, character=start_column),
            end=Position(line=end_line, character=end_column),
        )

    def get_byte_offset_from_line_pos(self, file: Path, line: int, col: int) -> int:
        if file not in self.__line_indexes:
            self.__line_indexes[file] = self.__setup_line_index(
                self.get_compiled_file(file).text
            )

        encoded_lines = self.__line_indexes[file]
        line_bytes, prefix = encoded_lines[line]
        line_offset = len(line_bytes.decode("utf-8")[:col].encode("utf-8"))
        return prefix + line_offset

    def get_early_byte_offset_from_line_pos(
        self, file: Path, line: int, col: int
    ) -> int:
        if file not in self.__early_line_indexes:
            self.__early_line_indexes[file] = self.__setup_line_index(
                self.early_opened_files[file].text
                if file in self.early_opened_files
                else file.read_text("utf-8")
            )

        encoded_lines = self.__early_line_indexes[file]
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

    async def __refresh_inlay_hints(self) -> None:
        try:
            await self.__server.send_request(RequestMethodEnum.INLAY_HINT_REFRESH, None)
        except LspError:
            pass

    async def _handle_change(
        self,
        change: Union[
            CustomFileChangeCommand,
            ConfigUpdate,
            CreateFilesParams,
            RenameFilesParams,
            DeleteFilesParams,
            FileEvent,
            DidOpenTextDocumentParams,
            DidCloseTextDocumentParams,
            DidChangeTextDocumentParams,
            None,
        ],
    ) -> None:
        # cannot rely on that a file is cleared from __discovered_files when deleted
        if isinstance(change, CustomFileChangeCommand):
            if change == CustomFileChangeCommand.FORCE_RECOMPILE:
                for file in self.__discovered_files:
                    # clear diagnostics
                    await self.__diagnostic_queue.put((file, set()))

                self.__interval_trees.clear()
                self.__source_units.clear()
                self.__ir_reference_resolver.clear_all_registered_nodes()
                self.__ir_reference_resolver.clear_all_indexed_nodes()
                self.__ir_reference_resolver.clear_all_cu_metadata()
                self.__latest_errors_per_cu = {}
                self.__compilation_errors = {}
                self.__cu_counter.clear()

                self.__discovered_files.clear()
                self.__compilation_errors.clear()
                if self.__perform_files_discovery:
                    while True:
                        try:
                            for f in glob.iglob(str(self.__config.project_root_path / "**/*.sol"), recursive=True):
                                file = Path(f)
                                if not self.__file_excluded(file) and file.is_file():
                                    self.__discovered_files.add(file.resolve())
                            break
                        except FileNotFoundError:
                            self.__discovered_files.clear()
                            await asyncio.sleep(0.1)

                for file in self.__opened_files.keys():
                    # opened files may contain files that are still opened in IDE but already deleted on FS
                    # ensure such files are not added to discovered files
                    if not self.__file_excluded(file) and file.is_file():
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
                if not self.__file_excluded(path) and path.suffix == ".sol":
                    self.__discovered_files.add(path)
                    self.__force_compile_files.add(path)
        elif isinstance(change, RenameFilesParams):
            for rename in change.files:
                old_path = uri_to_path(rename.old_uri)
                self.__deleted_files.add(old_path)
                self.__discovered_files.discard(old_path)
                self.__opened_files.pop(old_path, None)

                new_path = uri_to_path(rename.new_uri)
                if not self.__file_excluded(new_path) and new_path.suffix == ".sol":
                    self.__discovered_files.add(new_path)
                    self.__force_compile_files.add(new_path)
        elif isinstance(change, DeleteFilesParams):
            for delete in change.files:
                path = uri_to_path(delete.uri)
                self.__deleted_files.add(path)
                self.__discovered_files.discard(path)
                self.__opened_files.pop(path, None)
        elif isinstance(change, FileEvent):
            if change.type == FileChangeType.CREATED:
                path = uri_to_path(change.uri).resolve()
                if path.is_file() and path.suffix == ".sol":
                    if not self.__file_excluded(path):
                        self.__discovered_files.add(path)
                        self.__force_compile_files.add(path)
                    else:
                        self.__disk_changed_files.add(path)
            elif change.type == FileChangeType.DELETED:
                # cannot remove from __opened_files here because it may be still opened in IDE
                # a change to the deleted (but IDE-opened) file would cause a crash

                path = uri_to_path(change.uri).resolve()
                for p in list(self.__discovered_files):
                    if is_relative_to(p, path):
                        self.__discovered_files.remove(p)

                for p in list(self.__disk_changed_files):
                    if is_relative_to(p, path):
                        self.__disk_changed_files.remove(p)

                for p in list(self.__output_contents):
                    if is_relative_to(p, path):
                        self.__deleted_files.add(p)
            elif change.type == FileChangeType.CHANGED:
                path = uri_to_path(change.uri).resolve()
                if path.is_file() and path.suffix == ".sol":
                    if (
                        path not in self.__discovered_files
                        and not self.__file_excluded(path)
                    ):
                        self.__discovered_files.add(path)
                        self.__force_compile_files.add(path)
                    else:
                        self.__disk_changed_files.add(path)
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
            else:
                try:
                    if change.text_document.text != self.get_compiled_file(path).text:
                        self.__force_compile_files.add(path)
                except UnicodeDecodeError:
                    pass

        elif isinstance(change, DidCloseTextDocumentParams):
            path = uri_to_path(change.text_document.uri).resolve()
            self.__opened_files.pop(path, None)
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

    async def __check_target_versions(self, *, show_message: bool) -> None:
        min_version = self.__config.min_solidity_version
        max_version = self.__config.max_solidity_version

        for target_version in chain(
            [s.target_version for s in self.__config.subproject.values()],
            [self.__config.compiler.solc.target_version],
        ):
            if target_version is not None and target_version < min_version:
                message = f"The minimum supported version of Solidity is {min_version}. Version {target_version} is selected in settings."

                await self.__server.log_message(message, MessageType.WARNING)
                if show_message:
                    await self.__server.show_message(message, MessageType.WARNING)

                for file in self.__discovered_files:
                    # clear diagnostics
                    await self.__diagnostic_queue.put((file, set()))

                raise CompilationError("Invalid target version")
            if target_version is not None and target_version > max_version:
                message = f"The maximum supported version of Solidity is {max_version}. Version {target_version} is selected in settings."

                await self.__server.log_message(message, MessageType.WARNING)
                if show_message:
                    await self.__server.show_message(message, MessageType.WARNING)

                for file in self.__discovered_files:
                    # clear diagnostics
                    await self.__diagnostic_queue.put((file, set()))

                raise CompilationError("Invalid target version")

    async def __detect_target_versions(
        self, compilation_units: List[CompilationUnit], *, show_message: bool
    ) -> Tuple[List[SolidityVersion], List[CompilationUnit], List[str]]:
        min_version = self.__config.min_solidity_version
        max_version = self.__config.max_solidity_version
        target_versions = []
        skipped_compilation_units = []
        skipped_reasons = []

        for compilation_unit in compilation_units:
            target_version = (
                self.__config.compiler.solc.target_version
                if compilation_unit.subproject is None
                else self.__config.subproject[
                    compilation_unit.subproject
                ].target_version
            )
            if target_version is not None:
                if target_version not in compilation_unit.versions:
                    message = (
                        f"Unable to compile the following files with solc version `{target_version}` set in config:\n"
                        + "\n".join(
                            path_to_uri(path) for path in compilation_unit.files
                        )
                    )

                    await self.__server.log_message(message, MessageType.WARNING)
                    if show_message:
                        await self.__server.show_message(message, MessageType.WARNING)

                    skipped_compilation_units.append(compilation_unit)
                    skipped_reasons.append(
                        f"Cannot be compiled with version {target_version} set in config"
                    )
                    continue
            else:
                # use the latest matching version
                matching_versions = [
                    version
                    for version in reversed(self.__svm.list_all())
                    if version in compilation_unit.versions
                ]
                if len(matching_versions) == 0:
                    message = (
                        f"Unable to find a matching version of Solidity for the following files:\n"
                        + "\n".join(
                            path_to_uri(path) for path in compilation_unit.files
                        )
                    )

                    await self.__server.log_message(message, MessageType.WARNING)
                    if show_message:
                        await self.__server.show_message(message, MessageType.WARNING)

                    skipped_compilation_units.append(compilation_unit)
                    source_unit_names = "\n".join(compilation_unit.source_unit_names)
                    skipped_reasons.append(
                        f"Cannot be compiled with other files:\n{source_unit_names}"
                    )
                    continue
                try:
                    target_version = next(
                        version
                        for version in matching_versions
                        if version <= max_version
                    )
                except StopIteration:
                    message = (
                        f"The maximum supported version of Solidity is {max_version}, unable to compile the following files:\n"
                        + "\n".join(
                            path_to_uri(path) for path in compilation_unit.files
                        )
                    )

                    await self.__server.log_message(message, MessageType.WARNING)
                    if show_message:
                        await self.__server.show_message(message, MessageType.WARNING)

                    skipped_compilation_units.append(compilation_unit)
                    skipped_reasons.append(
                        f"Cannot be compiled due to the maximum supported version of Solidity being {max_version}"
                    )
                    continue

                if target_version < min_version:
                    message = (
                        f"The minimum supported version of Solidity is {min_version}, unable to compile the following files:\n"
                        + "\n".join(
                            path_to_uri(path) for path in compilation_unit.files
                        )
                    )

                    await self.__server.log_message(message, MessageType.WARNING)
                    if show_message:
                        await self.__server.show_message(message, MessageType.WARNING)

                    skipped_compilation_units.append(compilation_unit)
                    skipped_reasons.append(
                        f"Cannot be compiled due to the minimum supported version of Solidity being {min_version}"
                    )
                    continue
            target_versions.append(target_version)

        return target_versions, skipped_compilation_units, skipped_reasons

    async def __install_solc(self, target_versions: List[SolidityVersion]) -> None:
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

    async def bytecode_compile(
        self,
    ) -> Tuple[
        bool,
        Dict[str, SolcOutputContractInfo],
        Dict[str, Dict],
        Dict[str, Set[Tuple[str, Path, int, int]]],
        Dict[str, Tuple[str, Path]],
    ]:
        try:
            await self.__check_target_versions(show_message=True)
        except CompilationError:
            return False, {}, {}, {}, {}

        modified_files = {
            path: info.text.encode("utf-8")
            for path, info in self.__opened_files.items()
        }
        for p in self.__output_contents:
            if p not in modified_files:
                modified_files[p] = self.__output_contents[p].text.encode("utf-8")

        try:
            graph, source_units_to_paths = self.__compiler.build_graph(
                self.__discovered_files,
                modified_files,
                True,
            )
        except CompilationError as e:
            await self.__server.show_message(str(e), MessageType.ERROR)
            await self.__server.log_message(str(e), MessageType.ERROR)
            return False, {}, {}, {}, {}

        logging_buffer = []
        handler = LspLoggingHandler(logging_buffer)
        logger.addHandler(handler)

        compilation_units = self.__compiler.build_compilation_units_maximize(graph, logger)

        for log in logging_buffer:
            await self.__server.log_message(log[0], log[1])
        logging_buffer.clear()

        if len(compilation_units) == 0:
            return False, {}, {}, {}, {}

        subprojects = {cu.subproject for cu in compilation_units}
        build_settings = {
            subproject: self.__compiler.create_build_settings(
                [
                    SolcOutputSelectionEnum.ABI,
                    SolcOutputSelectionEnum.EVM_BYTECODE_OBJECT,
                    SolcOutputSelectionEnum.EVM_DEPLOYED_BYTECODE_OBJECT,
                    SolcOutputSelectionEnum.AST,
                ],
                subproject,
            )
            for subproject in subprojects
        }

        # optimization - merge compilation units that can be compiled together
        compilation_units = SolidityCompiler.merge_compilation_units(
            compilation_units, graph, self.__config
        )

        (
            target_versions,
            skipped_compilation_units,
            skipped_reasons,
        ) = await self.__detect_target_versions(compilation_units, show_message=True)

        skipped_source_units = {}
        for compilation_unit, reason in zip(skipped_compilation_units, skipped_reasons):
            for source_unit_name in compilation_unit.source_unit_names:
                skipped_source_units[source_unit_name] = (
                    reason,
                    compilation_unit.source_unit_name_to_path(source_unit_name),
                )

        compilation_units = [
            cu for cu in compilation_units if cu not in skipped_compilation_units
        ]
        assert len(compilation_units) == len(target_versions)

        await self.__install_solc(target_versions)

        progress_token = await self.__server.progress_begin("Compiling")

        tasks = []
        for compilation_unit, target_version in zip(compilation_units, target_versions):
            task = self.__server.create_task(
                self.__compiler.compile_unit_raw(
                    compilation_unit,
                    target_version,
                    build_settings[compilation_unit.subproject],
                    logger,
                )
            )
            tasks.append(task)

        # wait for compilation of all compilation units
        try:
            ret = await asyncio.gather(*tasks)
        except Exception as e:
            for task in tasks:
                task.cancel()
            await self.__server.show_message(str(e), MessageType.ERROR)
            await self.__server.log_message(str(e), MessageType.ERROR)
            if progress_token is not None:
                await self.__server.progress_end(progress_token)

            return False, {}, {}, {}, {}
        finally:
            logger.removeHandler(handler)

        for log in logging_buffer:
            await self.__server.log_message(log[0], log[1])

        contract_info: Dict[str, SolcOutputContractInfo] = {}
        asts: Dict[str, Dict] = {}
        errors: Dict[str, Set[Tuple[str, Path, int, int]]] = defaultdict(set)

        solc_output: SolcOutput
        for cu, solc_output in zip(compilation_units, ret):
            for error in solc_output.errors:
                # log errors without location
                if error.source_location is None:
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
                elif error.severity == SolcOutputErrorSeverityEnum.ERROR:
                    errors[error.source_location.file].add(
                        (
                            error.message,
                            cu.source_unit_name_to_path(error.source_location.file),
                            error.source_location.start,
                            error.source_location.end,
                        )
                    )

            for source_unit_name in solc_output.contracts.keys():
                if graph.nodes[source_unit_name]["subproject"] != cu.subproject:
                    continue

                for contract_name, info in solc_output.contracts[
                    source_unit_name
                ].items():
                    fqn = f"{source_unit_name}:{contract_name}"
                    if fqn in contract_info:
                        continue
                    contract_info[fqn] = info

            for source_unit_name, ast in solc_output.sources.items():
                if graph.nodes[source_unit_name]["subproject"] != cu.subproject:
                    continue

                skipped_source_units.pop(source_unit_name, None)

                if ast.ast is not None:
                    asts[source_unit_name] = ast.ast

        if progress_token is not None:
            await self.__server.progress_end(progress_token)

        return True, contract_info, asts, errors, skipped_source_units

    async def __compile(
        self,
        files_to_compile: Set[Path],
        compiled_files: Set[Path],
        executor: ThreadPoolExecutor,
        full_compile: bool = True,
        errors_per_cu: Optional[Dict[bytes, Set[SolcOutputError]]] = None,
        compilation_units_per_file: Optional[Dict[Path, Set[CompilationUnit]]] = None,
    ) -> bool:
        if errors_per_cu is None:
            errors_per_cu = {}
        if compilation_units_per_file is None:
            compilation_units_per_file = defaultdict(set)

        try:
            await self.__check_target_versions(show_message=False)
        except CompilationError:
            self.__interval_trees.clear()
            self.__source_units.clear()
            self.__ir_reference_resolver.clear_all_registered_nodes()
            self.__ir_reference_resolver.clear_all_indexed_nodes()
            self.__ir_reference_resolver.clear_all_cu_metadata()
            self.__last_graph = nx.DiGraph()
            self.__latest_errors_per_cu = {}
            return True

        try:
            modified_files = {f: f.read_bytes() for f in self.__disk_changed_files}
            for path, info in self.__opened_files.items():
                modified_files[path] = info.text.encode("utf-8")

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
                graph, source_units_to_paths = self.__compiler.build_graph(
                    files_to_compile,
                    modified_files,
                    True,
                )

        except CompilationError as e:
            await self.__server.log_message(str(e), MessageType.ERROR)
            for file in self.__discovered_files:
                # clear diagnostics
                await self.__diagnostic_queue.put((file, set()))
            self.__interval_trees.clear()
            self.__source_units.clear()
            self.__ir_reference_resolver.clear_all_registered_nodes()
            self.__ir_reference_resolver.clear_all_indexed_nodes()
            self.__ir_reference_resolver.clear_all_cu_metadata()
            self.__last_graph = nx.DiGraph()
            self.__latest_errors_per_cu = {}
            return True

        # whole CU may be deleted -> there are no CUs to compile
        # but errors still need to be cleared and callbacks run
        for deleted_file in self.__deleted_files:
            await self.__diagnostic_queue.put((deleted_file, []))
            if deleted_file in self.__source_units:
                self.__ir_reference_resolver.run_destroy_callbacks(deleted_file)
                self.__ir_reference_resolver.clear_registered_nodes([deleted_file])
                source_unit = self.__source_units.pop(deleted_file)
                self.__interval_trees.pop(deleted_file)
                self.__compilation_errors.pop(deleted_file, None)
                self.__cu_counter[source_unit.cu_hash] -= 1

        logging_buffer = []
        handler = LspLoggingHandler(logging_buffer)
        logger.addHandler(handler)

        compilation_units = self.__compiler.build_compilation_units_maximize(graph, logger)

        for log in logging_buffer:
            await self.__server.log_message(log[0], log[1])
        logging_buffer.clear()

        for source_unit_name in graph.nodes:
            path = graph.nodes[source_unit_name]["path"]
            content = graph.nodes[source_unit_name]["content"]
            if (
                path not in self.__output_contents
                or self.__output_contents[path].text.encode("utf-8") != content
            ):
                if path not in files_to_compile:
                    files_to_compile.add(path)

        # filter out only compilation units that need to be compiled
        needed_compilation_units = [
            cu
            for cu in compilation_units
            if (cu.files & files_to_compile)
            or cu.contains_unresolved_file(self.__deleted_files, self.__config)
        ]
        if len(needed_compilation_units) == 0:
            return len(self.__deleted_files) > 0

        for cu in set(compilation_units) - set(needed_compilation_units):
            for path in cu.files:
                if (
                    graph.nodes[next(iter(cu.path_to_source_unit_names(path)))][
                        "subproject"
                    ]
                    == cu.subproject
                ):
                    compilation_units_per_file[path].add(cu)

        compilation_units = needed_compilation_units
        subprojects = {cu.subproject for cu in compilation_units}

        build_settings = {
            subproject: self.__compiler.create_build_settings(
                [SolcOutputSelectionEnum.AST],
                subproject,
            )
            for subproject in subprojects
        }

        if full_compile:
            self.__last_build_settings = build_settings

        # optimization - merge compilation units that can be compiled together
        compilation_units = SolidityCompiler.merge_compilation_units(
            compilation_units, graph, self.__config
        )
        for cu in compilation_units:
            for path in cu.files:
                if (
                    graph.nodes[next(iter(cu.path_to_source_unit_names(path)))][
                        "subproject"
                    ]
                    == cu.subproject
                ):
                    compilation_units_per_file[path].add(cu)

        (
            target_versions,
            skipped_compilation_units,
            _,
        ) = await self.__detect_target_versions(compilation_units, show_message=False)
        await self.__install_solc(target_versions)

        for compilation_unit in skipped_compilation_units:
            for file in compilation_unit.files:
                try:
                    compilation_units_per_file[file].remove(compilation_unit)
                except KeyError:
                    # prevent triggering the following if condition multiple times
                    continue

                if len(compilation_units_per_file[file]) == 0:
                    # this file won't be present in the final build
                    # however, there may be other CUs compiling this file (for different subprojects) where compilation was successful
                    # to prevent the case where files from different subprojects depending on this file would be left orphaned,
                    # we need to remove them from the build as well
                    files = {source_units_to_paths[to] for (_, to) in nx.edge_bfs(graph, [
                        source_unit_name
                        for source_unit_name in graph.nodes
                        if graph.nodes[source_unit_name]["path"] == file
                    ])}
                    files.add(file)

                    for file in files:
                        # this file won't be taken from any CU, even if compiled successfully
                        compilation_units_per_file[file].clear()

                        # clear diagnostics
                        await self.__diagnostic_queue.put((file, set()))

                        if file in self.__interval_trees:
                            self.__interval_trees.pop(file)

                        if file in self.__source_units:
                            self.__ir_reference_resolver.run_destroy_callbacks(file)
                            self.__ir_reference_resolver.clear_registered_nodes([file])
                            source_unit = self.__source_units.pop(file)
                            self.__cu_counter[source_unit.cu_hash] -= 1

            compilation_units.remove(compilation_unit)

        progress_token = await self.__server.progress_begin("Compiling")

        tasks = []
        for compilation_unit, target_version in zip(compilation_units, target_versions):
            task = self.__server.create_task(
                self.__compiler.compile_unit_raw(
                    compilation_unit,
                    target_version,
                    build_settings[compilation_unit.subproject],
                    logger,
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
            self.__ir_reference_resolver.clear_all_registered_nodes()
            self.__ir_reference_resolver.clear_all_indexed_nodes()
            self.__ir_reference_resolver.clear_all_cu_metadata()
            self.__last_graph = nx.DiGraph()
            self.__latest_errors_per_cu = {}
            return True
        finally:
            logger.removeHandler(handler)

        for log in logging_buffer:
            await self.__server.log_message(log[0], log[1])

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
            self.__ir_reference_resolver.clear_all_registered_nodes()
            self.__ir_reference_resolver.clear_all_indexed_nodes()
            self.__ir_reference_resolver.clear_all_cu_metadata()
            self.__latest_errors_per_cu = errors_per_cu
            self.__compilation_errors = {}
            return True

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

        # we don't want to recompile files that we cannot compile due to version restrictions
        for skipped_compilation_unit in skipped_compilation_units:
            for file in skipped_compilation_unit.files:
                if not any(cu for cu in compilation_units if file in cu.files):
                    files_to_recompile.discard(file)

        successful_compilation_units = []
        for cu, solc_output in zip(compilation_units, ret):
            for file in cu.files:
                if file in self.__line_indexes:
                    self.__line_indexes.pop(file)
                if file in self.__opened_files:
                    self.__output_contents[file] = self.__opened_files[file]
                else:
                    try:
                        self.__output_contents[file] = VersionedFile(
                            graph.nodes[next(iter(cu.path_to_source_unit_names(file)))][
                                "content"
                            ].decode("utf-8"),
                            None,
                        )
                    except UnicodeDecodeError:
                        pass

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

                try:
                    compilation_units_per_file[file].remove(cu)
                except KeyError:
                    # prevent triggering the following if condition multiple times
                    continue

                if len(compilation_units_per_file[file]) == 0:
                    # this file won't be present in the final build
                    # however, there may be other CUs compiling this file (for different subprojects) where compilation was successful
                    # to prevent the case where files from different subprojects depending on this file would be left orphaned,
                    # we need to remove them from the build as well
                    files = {source_units_to_paths[to] for (_, to) in nx.edge_bfs(graph, [
                        source_unit_name
                        for source_unit_name in graph.nodes
                        if graph.nodes[source_unit_name]["path"] == file
                    ])}
                    files.add(file)

                    for file in files:
                        # this file won't be taken from any CU, even if compiled successfully
                        compilation_units_per_file[file].clear()

                        if file in self.__source_units:
                            self.__ir_reference_resolver.run_destroy_callbacks(file)
                            self.__ir_reference_resolver.clear_registered_nodes([file])
                            source_unit = self.__source_units.pop(file)
                            self.__cu_counter[source_unit.cu_hash] -= 1

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

        def index_new_nodes():
            ast_index: Dict[Path, List[Tuple[AstSolc, bytes]]] = defaultdict(list)

            for cu_index, (cu, solc_output) in enumerate(successful_compilation_units):
                # files requested to be compiled and files that import these files (even indirectly)
                recompiled_files: Set[Path] = set()
                _out_edge_bfs(cu, files_to_compile & cu.files, recompiled_files)

                for source_unit_name, raw_ast in solc_output.sources.items():
                    path: Path = cu.source_unit_name_to_path(source_unit_name)
                    ast = AstSolc.model_validate(raw_ast.ast)

                    files_to_recompile.discard(path)

                    if path in self.__source_units and path not in recompiled_files:
                        # file was not recompiled
                        # still need to index AST
                        self.__ir_reference_resolver.index_nodes(ast, path, cu.hash)
                        continue
                    elif path in processed_files:
                        # file was already processed
                        # index AST + register (possibly new) source unit name
                        self.__ir_reference_resolver.index_nodes(ast, path, cu.hash)
                        self.__source_units[path]._source_unit_names.add(ast.absolute_path)
                        continue
                    elif cu not in compilation_units_per_file[path]:
                        # file recompiled but canonical AST not indexed yet
                        # must be processed later to preserve the AST structure of the canonical AST
                        ast_index[path].append((ast, cu.hash))
                        continue

                    processed_files.add(path)

                    # process canonical AST first
                    self.__ir_reference_resolver.index_nodes(ast, path, cu.hash)

                    for prev_ast, prev_cu_hash in ast_index[path]:
                        self.__ir_reference_resolver.index_nodes(prev_ast, path, prev_cu_hash)

                    interval_tree = IntervalTree()
                    init = IrInitTuple(
                        path,
                        self.get_compiled_file(path).text.encode("utf-8"),
                        cu,
                        interval_tree,
                        self.__ir_reference_resolver,
                        None,
                    )
                    self.__ir_reference_resolver.clear_registered_nodes(
                        [path]
                    )  # prevents keeping in memory old nodes
                    if path in self.__source_units:
                        self.__cu_counter[self.__source_units[path].cu_hash] -= 1
                    self.__source_units[path] = SourceUnit(init, ast)
                    self.__interval_trees[path] = interval_tree

                    self.__cu_counter[cu.hash] += 1

                    compiled_files.add(path)

            # must be run after all CUs processed
            # this is due to callbacks may require source units present in same CU but precessed in different CU
            # source unit may be processed later in different CU due to subproject requirement
            self.__ir_reference_resolver.run_post_process_callbacks(
                CallbackParams(
                    interval_trees=self.__interval_trees,
                    source_units=self.__source_units,
                )
            )

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(executor, index_new_nodes)

        if progress_token is not None:
            await self.__server.progress_end(progress_token)

        self.__compilation_errors = deepcopy(errors_per_file)

        # send compiler warnings and errors first without waiting for detectors to finish
        for path, errors in errors_per_file.items():
            await self.__diagnostic_queue.put((path, errors))

        # only recompile files we are interested in
        files_to_recompile = {
            p for p in files_to_recompile if not self.__file_excluded(p)
        }

        if len(files_to_recompile) > 0:
            # avoid infinite recursion
            if files_to_recompile != files_to_compile or full_compile:
                await self.__compile(
                    files_to_recompile,
                    compiled_files,
                    executor,
                    False,
                    errors_per_cu,
                    compilation_units_per_file,
                )

        if full_compile:
            self.__latest_errors_per_cu = errors_per_cu

        return True

    async def __run_detectors_task(self, contents: Dict[Path, bytes]) -> None:
        if self.__detectors_task is not None:
            self.__detectors_task.cancel()

            try:
                await self.__detectors_task
            except asyncio.CancelledError:
                pass

        if self.__config.lsp.detectors.enable:
            self.__detectors_task = self.__server.create_task(
                self.__run_detectors(contents)
            )

    async def __run_printers_task(self, contents: Dict[Path, bytes]) -> None:
        if self.__printers_task is not None:
            self.__printers_task.cancel()

            try:
                await self.__printers_task
            except asyncio.CancelledError:
                pass

        self.__printers_task = self.__server.create_task(self.__run_printers(contents))

    async def __run_printers(self, contents: Dict[Path, bytes]) -> None:
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
                self.__printer_contents = contents

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
                self.__printer_code_lenses.clear()
                self.__printer_hovers.clear()
                self.__printer_inlay_hints.clear()
                self.__printer_contents.clear()

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
        await self.__refresh_inlay_hints()

    async def __run_detectors(self, contents: Dict[Path, bytes]) -> None:
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
                self.__detector_contents = contents

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
                self.__detector_code_lenses.clear()
                self.__detector_hovers.clear()
                self.__detector_inlay_hints.clear()
                self.__detector_contents.clear()

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
        await self.__refresh_inlay_hints()

    async def __compilation_loop(self):
        loop = asyncio.get_event_loop()

        with ThreadPoolExecutor(max_workers=1) as executor:
            updated_files: Set[Path] = set()

            if self.__perform_files_discovery:
                # perform Solidity files discovery
                while True:
                    try:
                        for f in glob.iglob(str(self.__config.project_root_path / "**/*.sol"), recursive=True):
                            file = Path(f)
                            if not self.__file_excluded(file) and file.is_file():
                                self.__discovered_files.add(file.resolve())
                        break
                    except FileNotFoundError:
                        self.__discovered_files.clear()
                        await asyncio.sleep(0.1)

                self.__force_compile_files.update(self.__discovered_files)

            start = time.perf_counter()
            while True:
                while True:
                    try:
                        change = self.__file_changes_queue.get_nowait()
                        start = time.perf_counter()
                        await self._handle_change(change)
                    except asyncio.QueueEmpty:
                        if (
                            time.perf_counter() - start
                            > self.__config.lsp.compilation_delay + 0.4
                        ):
                            break
                        await asyncio.sleep(0.1)

                # run the compilation
                if (
                    len(self.__force_compile_files) > 0
                    or len(self.__modified_files) > 0
                    or len(self.__deleted_files) > 0
                    or len(self.__disk_changed_files) > 0
                ):
                    new_build = await self.__compile(
                        self.__force_compile_files.union(self.__modified_files),
                        updated_files,
                        executor,
                    )

                    # clear CU metadata in reference resolver for CUs that are no longer in use
                    for cu_hash in list(self.__cu_counter):
                        if self.__cu_counter[cu_hash] == 0:
                            self.__ir_reference_resolver.clear_cu_metadata(cu_hash)
                            del self.__cu_counter[cu_hash]

                    if new_build:
                        self.__force_run_detectors = True
                        self.__force_run_printers = True

                    self.__force_compile_files.clear()
                    self.__modified_files.clear()
                    self.__deleted_files.clear()
                    self.__disk_changed_files.clear()

                if self.__file_changes_queue.empty():
                    self.compilation_ready.set()
                    self.__cache_ready.clear()

                    def update_cache():
                        for updated_file in updated_files:
                            # updated_file might got removed in one of the following __compile calls
                            if updated_file in self.__source_units:
                                self.__cache_diff_build(
                                    self.__source_units[updated_file]
                                )

                                self.__last_compilation_source_units[
                                    updated_file
                                ] = self.__source_units[updated_file]
                                self.__last_compilation_interval_trees[
                                    updated_file
                                ] = self.__interval_trees[updated_file]

                    await loop.run_in_executor(executor, update_cache)

                    self.__cache_ready.set()
                    updated_files.clear()

                    if self.__force_run_printers or self.__force_run_detectors:
                        build = {
                            "build_info": pickle.dumps(self.last_build_info),
                            "graph": pickle.dumps(self.last_graph),
                            "reference_resolver": pickle.dumps(
                                self.last_build.reference_resolver
                            ),
                            "source_units": {},
                        }
                        await asyncio.sleep(0)
                        for path in self.last_build.source_units:
                            build["source_units"][path] = pickle.dumps(
                                (
                                    self.last_build.source_units[path],
                                    self.last_build.interval_trees[path],
                                )
                            )
                            await asyncio.sleep(0)

                        if self.__force_run_printers:
                            self.send_subprocess_command(
                                self.__printers_subprocess,
                                SubprocessCommandType.BUILD,
                                build,
                            )
                            await self.__run_printers_task(
                                {
                                    path: source_unit.file_source
                                    for path, source_unit in self.last_build.source_units.items()
                                }
                            )
                        if self.__force_run_detectors:
                            self.send_subprocess_command(
                                self.__detectors_subprocess,
                                SubprocessCommandType.BUILD,
                                build,
                            )
                            await self.__run_detectors_task(
                                {
                                    path: source_unit.file_source
                                    for path, source_unit in self.last_build.source_units.items()
                                }
                            )

                    self.__force_run_detectors = False
                    self.__force_run_printers = False

                change = await self.__file_changes_queue.get()
                start = time.perf_counter()
                await self._handle_change(change)

    def __cache_diff_build(self, source_unit: SourceUnit):
        def resolve_go_to_def(
            node: Union[
                DeclarationAbc, SourceUnit, GlobalSymbol, Set[FunctionDefinition]
            ]
        ) -> Dict[Path, Set[Tuple[int, int]]]:
            ret = defaultdict(set)
            if isinstance(
                node, (FunctionDefinition, ModifierDefinition, VariableDeclaration)
            ):
                for decl in get_all_base_and_child_declarations(node):
                    if isinstance(decl, VariableDeclaration) or decl.implemented:
                        ret[decl.source_unit.file].add(decl.name_location)
                        self.__last_successful_compilation_contents[source_unit.file][
                            decl.source_unit.file
                        ] = decl.source_unit.file_source
            elif isinstance(node, SourceUnit):
                ret[node.file].add(node.byte_location)
                self.__last_successful_compilation_contents[source_unit.file][
                    node.file
                ] = node.file_source
            elif isinstance(node, GlobalSymbol):
                pass
            elif isinstance(node, set):
                for n in node:
                    ret.update(resolve_go_to_def(n))
            else:
                ret[node.source_unit.file].add(node.name_location)
                self.__last_successful_compilation_contents[source_unit.file][
                    node.source_unit.file
                ] = node.source_unit.file_source

            return ret

        def resolve_hover(
            original_node,
            node: Union[
                DeclarationAbc, SourceUnit, GlobalSymbol, Set[FunctionDefinition]
            ],
        ) -> None:
            if isinstance(node, DeclarationAbc):
                self.hover_cache[
                    original_node
                ] = f"```solidity\n{node.declaration_string}\n```"
            elif isinstance(node, set):
                self.hover_cache[original_node] = "\n".join(
                    f"```solidity\n{n.declaration_string}\n```" for n in node
                )

        def resolve_go_to_type_def(original_node, node) -> None:
            if not isinstance(node, VariableDeclaration):
                return

            type_name = node.type_name
            if isinstance(type_name, UserDefinedTypeName):
                ref_decl = type_name.referenced_declaration

                self.__last_successful_compilation_contents[source_unit.file][
                    ref_decl.source_unit.file
                ] = ref_decl.source_unit.file_source
                self.go_to_type_definition_cache[original_node] = (
                    ref_decl.source_unit.file,
                    ref_decl.name_location[0],
                    ref_decl.name_location[1],
                )

        self.__last_successful_compilation_contents[source_unit.file] = {
            source_unit.file: source_unit.file_source
        }

        for node in source_unit:
            if isinstance(node, (Identifier, MemberAccess)):
                ref_decl = node.referenced_declaration
                self.go_to_definition_cache[node] = resolve_go_to_def(ref_decl)
                resolve_hover(node, ref_decl)
                resolve_go_to_type_def(node, ref_decl)
            elif isinstance(node, (IdentifierPath, UserDefinedTypeName)):
                for part in node.identifier_path_parts:
                    ref_decl = part.referenced_declaration
                    self.go_to_definition_cache[part] = resolve_go_to_def(ref_decl)
                    resolve_hover(part, ref_decl)
                    resolve_go_to_type_def(part, ref_decl)
            elif (
                isinstance(node, YulIdentifier) and node.external_reference is not None
            ):
                ref_decl = node.external_reference.referenced_declaration
                self.go_to_definition_cache[node] = resolve_go_to_def(ref_decl)
                resolve_hover(node, ref_decl)
                resolve_go_to_type_def(node, ref_decl)
            elif (
                isinstance(node, (UnaryOperation, BinaryOperation))
                and node.function is not None
            ):
                function = node.function
                self.go_to_definition_cache[node] = resolve_go_to_def(function)
                resolve_hover(node, function)
            elif isinstance(node, VariableDeclaration):
                resolve_go_to_type_def(node, node)

    def __setup_line_index(self, content: str):
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
        return encoded_lines

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
