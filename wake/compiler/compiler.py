from __future__ import annotations

import asyncio
import json
import logging
import os
import pickle
import time
from bisect import bisect
from collections import defaultdict, deque
from contextlib import nullcontext
from json import JSONDecodeError
from pathlib import Path
from types import MappingProxyType
from typing import (
    Callable,
    Collection,
    DefaultDict,
    Deque,
    Dict,
    FrozenSet,
    Iterable,
    List,
    Mapping,
    Optional,
    Set,
    Tuple,
)

import networkx as nx
import rich
import rich.console
import rich.panel
from Crypto.Hash import BLAKE2b
from intervaltree import IntervalTree
from pathvalidate import sanitize_filename  # type: ignore
from pydantic import ValidationError
from rich.progress import Progress
from watchdog.events import (
    FileSystemEvent,
    FileSystemEventHandler,
    FileSystemMovedEvent,
)

from wake.config import WakeConfig
from wake.core import get_logger
from wake.core.solidity_version import (
    SolidityVersion,
    SolidityVersionRange,
    SolidityVersionRanges,
)
from wake.core.wake_comments import WakeComment, error_commented_out
from wake.ir import (
    ContractDefinition,
    EnumDefinition,
    ErrorDefinition,
    EventDefinition,
    FunctionDefinition,
    ModifierDefinition,
    SourceUnit,
    StructDefinition,
    UserDefinedValueTypeDefinition,
    VariableDeclaration,
)
from wake.ir.ast import AstSolc
from wake.ir.reference_resolver import CallbackParams, ReferenceResolver
from wake.ir.utils import IrInitTuple
from wake.regex_parser import SoliditySourceParser
from wake.svm import SolcVersionManager

from ..utils import get_package_version
from ..utils.file_utils import is_relative_to
from ..utils.keyed_default_dict import KeyedDefaultDict
from .build_data_model import (
    CompilationUnitBuildInfo,
    ProjectBuild,
    ProjectBuildInfo,
    SourceUnitInfo,
)
from .compilation_unit import CompilationUnit
from .exceptions import CompilationError, CompilationResolveError
from .solc_frontend import (
    SolcFrontend,
    SolcInputOptimizerDetailsSettings,
    SolcInputOptimizerSettings,
    SolcInputOptimizerYulDetailsSettings,
    SolcInputSettings,
    SolcOutput,
    SolcOutputError,
    SolcOutputErrorSeverityEnum,
    SolcOutputSelectionEnum,
)
from .source_path_resolver import SourcePathResolver
from .source_unit_name_resolver import SourceUnitNameResolver

# pyright: reportGeneralTypeIssues=false

logger = get_logger(__name__)


class CompilationFileSystemEventHandler(FileSystemEventHandler):
    _config: WakeConfig
    _files: Set[Path]
    _compiler: SolidityCompiler
    _output_types: Collection[SolcOutputSelectionEnum]
    _write_artifacts: bool
    _console: Optional[rich.console.Console]
    _no_warnings: bool
    _created_files: Set[Path]
    _modified_files: Set[Path]
    _deleted_files: Set[Path]
    _config_changed: bool
    _loop: asyncio.AbstractEventLoop
    _queue: asyncio.Queue[FileSystemEvent]
    _callbacks: List[Callable[[ProjectBuild, ProjectBuildInfo], None]]

    TIMEOUT_INTERVAL = 1.0

    def __init__(
        self,
        config: WakeConfig,
        files: Iterable[Path],
        loop: asyncio.AbstractEventLoop,
        compiler: SolidityCompiler,
        output_types: Collection[SolcOutputSelectionEnum],
        *,
        write_artifacts: bool = True,
        console: Optional[rich.console.Console] = None,
        no_warnings: bool = False,
    ):
        self._config = config
        self._files = set(files)
        self._loop = loop
        self._compiler = compiler
        self._output_types = output_types
        self._write_artifacts = write_artifacts
        self._console = console
        self._no_warnings = no_warnings
        self._created_files = set()
        self._modified_files = set()
        self._deleted_files = set()
        self._config_changed = False
        self._queue = asyncio.Queue()
        self._callbacks = []

    async def run(self):
        while True:
            # process at least one event
            event = await self._queue.get()
            self._process_event(event)

            start = time.perf_counter()
            while time.perf_counter() - start < self.TIMEOUT_INTERVAL:
                try:
                    event = self._queue.get_nowait()
                    self._process_event(event)
                except asyncio.QueueEmpty:
                    await asyncio.sleep(0.1)

            await self._compile()

            assert self._compiler.latest_build is not None
            assert self._compiler.latest_build_info is not None

            for callback in self._callbacks:
                callback(self._compiler.latest_build, self._compiler.latest_build_info)

    def register_callback(
        self, callback: Callable[[ProjectBuild, ProjectBuildInfo], None]
    ):
        self._callbacks.append(callback)

    def unregister_callback(
        self, callback: Callable[[ProjectBuild, ProjectBuildInfo], None]
    ):
        self._callbacks.remove(callback)

    def _process_event(self, event: FileSystemEvent):
        if isinstance(event, FileSystemMovedEvent):
            self._on_deleted(Path(event.src_path))
            self._on_created(Path(event.dest_path))
        elif event.event_type == "created":
            self._on_created(Path(event.src_path))
        elif event.event_type == "modified":
            self._on_modified(Path(event.src_path))
        elif event.event_type == "deleted":
            self._on_deleted(Path(event.src_path))

    def on_any_event(self, event: FileSystemEvent):
        if event.is_directory:
            return
        if isinstance(event, FileSystemMovedEvent):
            src_file = Path(event.src_path)
            dest_file = Path(event.dest_path)
            if (
                src_file == self._config.local_config_path
                or src_file.suffix == ".sol"
                or dest_file == self._config.local_config_path
                or dest_file.suffix == ".sol"
            ):
                self._loop.call_soon_threadsafe(self._queue.put_nowait, event)
        else:
            file = Path(event.src_path)
            if file == self._config.local_config_path or file.suffix == ".sol":
                self._loop.call_soon_threadsafe(self._queue.put_nowait, event)

    async def _compile(self):
        if self._config_changed:
            self._config.load_configs()

            # find files that were previously ignored but are now included
            ctx_manager = (
                self._console.status("[bold green]Searching for *.sol files...[/]")
                if self._console
                else nullcontext()
            )
            start = time.perf_counter()
            files = set()
            with ctx_manager:
                for file in self._config.project_root_path.rglob("**/*.sol"):
                    if (
                        not any(
                            is_relative_to(file, p)
                            for p in self._config.compiler.solc.exclude_paths
                        )
                        and file.is_file()
                    ):
                        files.add(file)
            end = time.perf_counter()
            if self._console is not None:
                self._console.log(
                    f"[green]Found {len(files)} *.sol files in [bold green]{end - start:.2f} s[/bold green][/]"
                )

            deleted_files = self._deleted_files
        else:
            files = self._files.copy()
            files.update(self._created_files)
            files.update(self._modified_files)
            ignored_files = {
                f
                for f in files
                if any(
                    is_relative_to(f, p)
                    for p in self._config.compiler.solc.exclude_paths
                )
                or not is_relative_to(f, self._config.project_root_path)
            }
            files.difference_update(ignored_files)
            files.difference_update(self._deleted_files)
            deleted_files = self._deleted_files

        await self._compiler.compile(
            files,
            self._output_types,
            write_artifacts=self._write_artifacts,
            deleted_files=deleted_files,
            console=self._console,
            no_warnings=self._no_warnings,
        )

        self._created_files.clear()
        self._modified_files.clear()
        self._deleted_files.clear()
        self._config_changed = False

    def _on_created(self, file: Path):
        if file == self._config.local_config_path:
            self._config_changed = True
        elif file.suffix == ".sol":
            self._files.add(file)
            if file in self._deleted_files:
                self._deleted_files.remove(file)
                self._modified_files.add(file)
            else:
                logger.debug(f"File {file} created")
                self._created_files.add(file)

    def _on_modified(self, file: Path):
        if file == self._config.local_config_path:
            self._config_changed = True
        elif file.suffix == ".sol":
            logger.debug(f"File {file} modified")
            self._modified_files.add(file)

    def _on_deleted(self, file: Path):
        if file == self._config.local_config_path:
            self._config_changed = True
        elif file.suffix == ".sol":
            try:
                self._files.remove(file)
            except KeyError:
                pass
            if file in self._modified_files:
                self._modified_files.remove(file)

            if file in self._created_files:
                self._created_files.remove(file)
            else:
                logger.debug(f"File {file} deleted")
                self._deleted_files.add(file)


class SolidityCompiler:
    __config: WakeConfig
    __svm: SolcVersionManager
    __solc_frontend: SolcFrontend
    __source_unit_name_resolver: SourceUnitNameResolver
    __source_path_resolver: SourcePathResolver

    _latest_build_info: Optional[ProjectBuildInfo]
    _latest_build: Optional[ProjectBuild]
    _latest_graph: Optional[nx.DiGraph]
    _latest_source_units_to_paths: Optional[Dict[str, Path]]

    _lines_index: Dict[Path, List[int]]

    def __init__(self, wake_config: WakeConfig):
        self.__config = wake_config
        self.__svm = SolcVersionManager(wake_config)
        self.__solc_frontend = SolcFrontend(wake_config)
        self.__source_unit_name_resolver = SourceUnitNameResolver(wake_config)
        self.__source_path_resolver = SourcePathResolver(wake_config)

        self._latest_build_info = None
        self._latest_build = None
        self._latest_graph = None
        self._latest_source_units_to_paths = None

        self._lines_index = {}

    @property
    def latest_build_info(self) -> Optional[ProjectBuildInfo]:
        return self._latest_build_info

    @property
    def latest_build(self) -> Optional[ProjectBuild]:
        return self._latest_build

    @property
    def latest_graph(self) -> Optional[nx.DiGraph]:
        return self._latest_graph

    @property
    def latest_source_units_to_paths(self) -> Optional[MappingProxyType[str, Path]]:
        return MappingProxyType(self._latest_source_units_to_paths)

    def _get_line_from_offset(self, path: Path, offset: int, content: bytes) -> int:
        if path not in self._lines_index:
            prefix_sum = 0
            self._lines_index[path] = []

            for line in content.splitlines(keepends=True):
                prefix_sum += len(line)
                self._lines_index[path].append(prefix_sum)

        return bisect(self._lines_index[path], offset)

    def _prepare_wake_comments(
        self,
        path: Path,
        content: bytes,
        wake_comments: Dict[str, List[Tuple[List[str], Tuple[int, int]]]],
    ) -> Dict[str, Dict[int, WakeComment]]:
        prepared = {}
        for comment_type, comments in wake_comments.items():
            prepared[comment_type] = {}
            for codes, (start, end) in comments:
                start_line = self._get_line_from_offset(path, start, content)
                end_line = self._get_line_from_offset(path, end, content)

                prepared[comment_type][end_line] = WakeComment(
                    codes if codes else None,
                    start_line,
                    end_line,
                )
        return prepared

    def build_graph(
        self,
        files: Iterable[Path],
        modified_files: Mapping[Path, bytes],
        ignore_errors: bool = False,
    ) -> Tuple[nx.DiGraph, Dict[str, Path]]:
        self._lines_index.clear()

        # source unit name, full path, file content
        source_units_queue: deque[Tuple[str, Path, Optional[bytes]]] = deque()
        source_units: Dict[str, Path] = {}

        # for every source file resolve a source unit name
        for file in files:
            try:
                file = file.resolve(strict=True)
            except FileNotFoundError:
                if file in modified_files:
                    pass
                elif ignore_errors:
                    continue
                else:
                    raise

            source_unit_name = self.__source_unit_name_resolver.resolve_cmdline_arg(
                str(file)
            )
            if source_unit_name in source_units:
                first = str(source_units[source_unit_name])
                second = str(file)
                raise CompilationError(
                    f"Same source unit name `{source_unit_name}` for multiple source files:\n{first}\n{second}"
                )
            source_units[source_unit_name] = file
            content = modified_files.get(file, None)
            source_units_queue.append((source_unit_name, file, content))

        graph = nx.DiGraph()

        # recursively process all sources
        while len(source_units_queue) > 0:
            source_unit_name, path, content = source_units_queue.pop()
            if content is None:
                try:
                    (
                        versions,
                        imports,
                        h,
                        content,
                        wake_comments,
                    ) = SoliditySourceParser.parse(path, ignore_errors)
                except UnicodeDecodeError:
                    continue
            else:
                versions, imports, h, wake_comments = SoliditySourceParser.parse_source(
                    content, ignore_errors
                )
            graph.add_node(
                source_unit_name,
                path=path,
                versions=versions,
                hash=h,
                content=content,
                unresolved_imports=set(),
                wake_comments=self._prepare_wake_comments(path, content, wake_comments),
            )
            source_units[source_unit_name] = path

            for _import in imports:
                import_unit_name = self.__source_unit_name_resolver.resolve_import(
                    source_unit_name, _import
                )
                try:
                    import_path = self.__source_path_resolver.resolve(
                        import_unit_name, source_unit_name, modified_files.keys()
                    ).resolve()
                    if import_path not in modified_files:
                        import_path = import_path.resolve(strict=True)
                except (FileNotFoundError, CompilationResolveError):
                    if ignore_errors:
                        graph.nodes[source_unit_name]["unresolved_imports"].add(
                            import_unit_name
                        )
                        continue
                    raise

                if import_unit_name in source_units:
                    other_path = source_units[import_unit_name]
                    if import_path != other_path:
                        raise ValueError(
                            f"Same source unit name `{import_unit_name}` for multiple source files:\n{import_path}\n{other_path}"
                        )
                else:
                    source_units_queue.append(
                        (
                            import_unit_name,
                            import_path,
                            modified_files.get(import_path, None),
                        )
                    )
                graph.add_edge(import_unit_name, source_unit_name)
        return graph, source_units

    @staticmethod
    def build_compilation_units_maximize(graph: nx.DiGraph) -> List[CompilationUnit]:
        """
        Builds a list of compilation units from a graph. Number of compilation units is maximized.
        """

        def __build_compilation_unit(
            graph: nx.DiGraph, start: Iterable[str]
        ) -> CompilationUnit:
            nodes_subset = set()
            nodes_queue: deque[str] = deque(start)
            versions: SolidityVersionRanges = SolidityVersionRanges(
                [SolidityVersionRange(None, None, None, None)]
            )

            while len(nodes_queue) > 0:
                node = nodes_queue.pop()
                versions &= graph.nodes[node]["versions"]

                if node in nodes_subset:
                    continue
                nodes_subset.add(node)

                for in_edge in graph.in_edges(node):
                    _from, to = in_edge
                    if _from not in nodes_subset:
                        nodes_queue.append(_from)

            subgraph = graph.subgraph(nodes_subset).copy()
            return CompilationUnit(subgraph, versions)

        sinks = [node for node, out_degree in graph.out_degree() if out_degree == 0]
        compilation_units = []

        for sink in sinks:
            compilation_unit = __build_compilation_unit(graph, [sink])
            compilation_units.append(compilation_unit)

        # cycles can also be "sinks" in terms of compilation units
        generated_cycles: Set[FrozenSet[str]] = set()
        simple_cycles = [set(c) for c in nx.simple_cycles(graph)]
        for simple_cycle in simple_cycles:
            if any(simple_cycle.issubset(c) for c in generated_cycles):
                # this cycle was already merged with another cycle
                continue

            # merge with as many other cycles as possible (create transitive closure)
            for other_cycle in simple_cycles:
                if len(simple_cycle & other_cycle) > 0:
                    simple_cycle |= other_cycle

            is_closed_cycle = True
            for node in simple_cycle:
                if any(edge[1] not in simple_cycle for edge in graph.out_edges(node)):
                    is_closed_cycle = False
                    break

            if is_closed_cycle:
                generated_cycles.add(frozenset(simple_cycle))
                compilation_unit = __build_compilation_unit(graph, simple_cycle)
                compilation_units.append(compilation_unit)

        return compilation_units

    def create_build_settings(
        self, output_types: Collection[SolcOutputSelectionEnum]
    ) -> SolcInputSettings:
        settings = SolcInputSettings()  # type: ignore
        # TODO Allow setting all solc build settings
        # Currently it is not possible to set all solc standard JSON input build settings.
        # These include: stopAfter, optimizer, via_IR, debug, metadata, libraries and model checker settings.
        # See https://docs.soliditylang.org/en/v0.8.12/using-the-compiler.html#input-description.
        # Also it is not possible to specify solc output per contract or per source file.
        settings.remappings = [
            str(remapping) for remapping in self.__config.compiler.solc.remappings
        ]
        settings.evm_version = self.__config.compiler.solc.evm_version
        settings.via_IR = self.__config.compiler.solc.via_IR
        settings.optimizer = SolcInputOptimizerSettings(
            enabled=self.__config.compiler.solc.optimizer.enabled,
            runs=self.__config.compiler.solc.optimizer.runs,
            details=SolcInputOptimizerDetailsSettings(
                peephole=self.__config.compiler.solc.optimizer.details.peephole,
                inliner=self.__config.compiler.solc.optimizer.details.inliner,
                jumpdest_remover=self.__config.compiler.solc.optimizer.details.jumpdest_remover,
                order_literals=self.__config.compiler.solc.optimizer.details.order_literals,
                deduplicate=self.__config.compiler.solc.optimizer.details.deduplicate,
                cse=self.__config.compiler.solc.optimizer.details.cse,
                constant_optimizer=self.__config.compiler.solc.optimizer.details.constant_optimizer,
                simple_counter_for_loop_unchecked_increment=self.__config.compiler.solc.optimizer.details.simple_counter_for_loop_unchecked_increment,
            ),
        )

        if (
            self.__config.compiler.solc.optimizer.details.yul_details.stack_allocation
            is not None
            or self.__config.compiler.solc.optimizer.details.yul_details.optimizer_steps
            is not None
        ):
            assert settings.optimizer.details is not None
            settings.optimizer.details.yul_details = SolcInputOptimizerYulDetailsSettings(
                stack_allocation=self.__config.compiler.solc.optimizer.details.yul_details.stack_allocation,
                optimizer_steps=self.__config.compiler.solc.optimizer.details.yul_details.optimizer_steps,
            )

        settings.output_selection = {"*": {}}

        if SolcOutputSelectionEnum.ALL in output_types:
            settings.output_selection["*"][""] = [SolcOutputSelectionEnum.AST]  # type: ignore
            settings.output_selection["*"]["*"] = [SolcOutputSelectionEnum.ALL]  # type: ignore
        else:
            if SolcOutputSelectionEnum.AST in output_types:
                settings.output_selection["*"][""] = [SolcOutputSelectionEnum.AST]  # type: ignore
            settings.output_selection["*"]["*"] = [
                output_type
                for output_type in output_types
                if output_type != SolcOutputSelectionEnum.AST
            ]  # type: ignore

        return settings

    def determine_solc_versions(
        self, compilation_units: Iterable[CompilationUnit]
    ) -> List[SolidityVersion]:
        target_versions = []
        min_version = self.__config.min_solidity_version
        max_version = self.__config.max_solidity_version
        for compilation_unit in compilation_units:
            target_version = self.__config.compiler.solc.target_version
            if target_version is not None:
                if target_version not in compilation_unit.versions:
                    files_str = "\n".join(str(path) for path in compilation_unit.files)
                    raise CompilationError(
                        f"Unable to compile following files with solc version `{target_version}` set in config files:\n"
                        + files_str
                    )
            else:
                # use the latest matching version
                matching_versions = [
                    version
                    for version in reversed(self.__svm.list_all())
                    if version in compilation_unit.versions
                ]
                if len(matching_versions) == 0:
                    files_str = "\n".join(str(path) for path in compilation_unit.files)
                    raise CompilationError(
                        f"Unable to compile following files with any solc version:\n"
                        + files_str
                    )
                try:
                    target_version = next(
                        version
                        for version in matching_versions
                        if version <= max_version
                    )
                except StopIteration:
                    files_str = "\n".join(str(path) for path in compilation_unit.files)
                    raise CompilationError(
                        f"The maximum supported version of Solidity is {max_version}, unable to compile the following files:\n"
                        + files_str,
                    )
                if target_version < min_version:
                    files_str = "\n".join(str(path) for path in compilation_unit.files)
                    raise CompilationError(
                        f"The minimum supported version of Solidity is {min_version}, unable to compile the following files:\n"
                        + files_str,
                    )
            target_versions.append(target_version)
        return target_versions

    async def _install_solc(
        self,
        versions: Iterable[SolidityVersion],
        console: Optional[rich.console.Console],
    ) -> None:
        for version in set(versions):
            if not self.__svm.installed(version):
                if console is None:
                    await self.__svm.install(version)
                else:
                    with Progress(console=console) as progress:
                        task = progress.add_task(
                            f"[green]Downloading solc {version}", total=1
                        )

                        async def on_progress(downloaded: int, total: int) -> None:
                            progress.update(task, completed=downloaded, total=total)  # type: ignore

                        await self.__svm.install(
                            version,
                            progress=on_progress,
                        )

    @staticmethod
    def _out_edge_bfs(
        cu: CompilationUnit, start: Iterable[Path], out: Set[Path]
    ) -> None:
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

    def load(self, *, console: Optional[rich.console.Console] = None) -> None:
        ctx_manager = (
            console.status("[bold green]Loading previous build...")
            if console is not None
            else nullcontext()
        )
        start = time.perf_counter()

        with ctx_manager:
            try:
                latest_build_path = self.__config.project_root_path / ".wake" / "build"
                build_info = ProjectBuildInfo.parse_file(
                    latest_build_path / "build.json"
                )
                build_data = (latest_build_path / "build.bin").read_bytes()

                if build_info.wake_version != get_package_version("eth-wake"):
                    if console is not None:
                        console.log(
                            f"[yellow]Wake version changed from {build_info.wake_version} to {get_package_version('eth-wake')} since the last build[/yellow]"
                        )
                    return

                build_key_path = self.__config.global_data_path / "build.key"
                if not build_key_path.is_file():
                    if console is not None:
                        console.log(
                            f"[yellow]No build key found, cannot verify build signature.[/yellow]"
                        )
                build_key = build_key_path.read_bytes()
                if len(build_key) != 64:
                    if console is not None:
                        console.log(
                            f"[yellow]Loaded build key with incorrect length, cannot verify build signature.[/yellow]"
                        )
                    return

                build_sig = (latest_build_path / "build.bin.sig").read_bytes()

                h = BLAKE2b.new(digest_bits=512, key=build_key)
                h.update(build_data)
                h.verify(build_sig)

                self._latest_build = pickle.loads(build_data)
                self._latest_build_info = build_info
            except (
                AttributeError,
                ModuleNotFoundError,
                ValidationError,
                JSONDecodeError,
                FileNotFoundError,
                pickle.UnpicklingError,
                ValueError,
            ):
                if console is not None:
                    console.log("[red]Failed to load previous build artifacts[/red]")
                return

        if console is not None:
            end = time.perf_counter()
            console.log(
                f"[green]Loaded previous build in [bold green]{end - start:.2f} s[/bold green]"
            )

    @staticmethod
    def merge_compilation_units(
        compilation_units: List[CompilationUnit],
        graph: nx.DiGraph,
    ) -> List[CompilationUnit]:
        # optimization - merge compilation units that can be compiled together
        if len(compilation_units) > 0 and all(
            len(cu.versions) for cu in compilation_units
        ):
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

            logger.debug(
                f"Merged {len(compilation_units)} compilation units into {len(merged_compilation_units)}"
            )
            compilation_units = merged_compilation_units

        return compilation_units

    async def compile(
        self,
        files: Iterable[Path],
        output_types: Collection[SolcOutputSelectionEnum],
        *,
        write_artifacts: bool = True,
        force_recompile: bool = False,
        modified_files: Optional[Mapping[Path, bytes]] = None,
        deleted_files: Optional[
            Set[Path]
        ] = None,  # files that should be treated as deleted even if they exist
        console: Optional[rich.console.Console] = None,
        no_warnings: bool = False,
        incremental: Optional[bool] = None,
    ) -> Tuple[ProjectBuild, Set[SolcOutputError]]:
        if modified_files is None:
            modified_files = {}
        if deleted_files is None:
            deleted_files = set()

        if incremental is None:
            if force_recompile or self._latest_build_info is None:
                incremental = True
            else:
                incremental = self._latest_build_info.incremental

        # validate target solc version (if set)
        target_version = self.__config.compiler.solc.target_version
        min_version = self.__config.min_solidity_version
        max_version = self.__config.max_solidity_version
        if target_version is not None and target_version < min_version:
            raise CompilationError(
                f"Target configured version {target_version} is lower than minimum supported version {min_version}"
            )
        if target_version is not None and target_version > max_version:
            raise CompilationError(
                f"Target configured version {target_version} is higher than maximum supported version {max_version}"
            )

        graph, source_units_to_paths = self.build_graph(
            files, modified_files, ignore_errors=True
        )
        compilation_units = self.build_compilation_units_maximize(graph)
        build_settings = self.create_build_settings(output_types)

        self._latest_graph = graph
        self._latest_source_units_to_paths = source_units_to_paths

        build_settings_changed = False
        if self._latest_build_info is not None:
            if (
                self._latest_build_info.allow_paths
                != self.__config.compiler.solc.allow_paths
                or self._latest_build_info.exclude_paths
                != self.__config.compiler.solc.exclude_paths
                or self._latest_build_info.include_paths
                != self.__config.compiler.solc.include_paths
                or self._latest_build_info.settings != build_settings
                or self._latest_build_info.target_solidity_version
                != self.__config.compiler.solc.target_version
                or self._latest_build_info.incremental != incremental
            ):
                logger.debug("Build settings changed")
                build_settings_changed = True

        errors_per_cu: DefaultDict[bytes, Set[SolcOutputError]] = defaultdict(set)

        if (
            force_recompile
            or self._latest_build_info is None
            or self._latest_build is None
            or build_settings_changed
        ):
            logger.debug("Performing full recompile")
            build = ProjectBuild(
                interval_trees={},
                reference_resolver=ReferenceResolver(),
                source_units={},
            )
            files_to_compile = set(
                source_units_to_paths[source_unit] for source_unit in graph.nodes
            )

            if not incremental:
                compilation_units = self.merge_compilation_units(
                    compilation_units, graph
                )
        else:
            # TODO this is not needed? graph contains hash of modified files
            # files_to_compile = set(modified_files.keys())
            files_to_compile = set()

            for source_unit in graph.nodes:
                if (
                    source_unit not in self._latest_build_info.source_units_info
                    or self._latest_build_info.source_units_info[
                        source_unit
                    ].blake2b_hash
                    != graph.nodes[source_unit]["hash"]
                ):
                    files_to_compile.add(source_units_to_paths[source_unit])

            for source_unit, info in self._latest_build_info.source_units_info.items():
                if source_unit not in graph.nodes:
                    deleted_files.add(info.fs_path)

            if not incremental:
                compilation_units = self.merge_compilation_units(
                    compilation_units, graph
                )

            for cu_hash, cu_data in self._latest_build_info.compilation_units.items():
                if any(cu.hash.hex() == cu_hash for cu in compilation_units):
                    errors_per_cu[bytes.fromhex(cu_hash)] = set(cu_data.errors)

            # select only compilation units that need to be compiled
            compilation_units = [
                cu
                for cu in compilation_units
                if (cu.files & files_to_compile)
                or cu.contains_unresolved_file(deleted_files, self.__config)
            ]

            logger.debug(
                f"Recompiling {len(files_to_compile)} files and {len(compilation_units)} compilation units"
            )

            build = self._latest_build

        target_versions = self.determine_solc_versions(compilation_units)
        await self._install_solc(target_versions, console)

        tasks = []
        for compilation_unit, target_version in zip(compilation_units, target_versions):
            task = asyncio.create_task(
                self.compile_unit_raw(compilation_unit, target_version, build_settings)
            )
            tasks.append(task)

        logger.debug(f"Compiling {len(compilation_units)} compilation units")
        files = set()
        for cu in compilation_units:
            files |= cu.files

        ctx_manager = (
            console.status(
                f"[bold green]Compiling {len(files)} files using {len(compilation_units)} solc runs...[/]"
            )
            if console
            else nullcontext()
        )
        start = time.perf_counter()

        with ctx_manager:
            # wait for compilation of all compilation units
            try:
                ret: Tuple[SolcOutput, ...] = await asyncio.gather(*tasks)
            except Exception:
                for task in tasks:
                    task.cancel()
                raise

        end = time.perf_counter()
        if console is not None:
            console.log(
                f"[green]Compiled {len(files)} files using {len(compilation_units)} solc runs in [bold green]{end - start:.2f} s[/bold green][/]"
            )

        # remove deleted files from the previous build
        for deleted_file in deleted_files:
            if deleted_file in build.source_units:
                build.reference_resolver.run_destroy_callbacks(deleted_file)
                build._source_units.pop(deleted_file)

        ctx_manager = (
            console.status(f"[bold green]Processing compilation results...[/]")
            if console
            else nullcontext()
        )
        start = time.perf_counter()

        symbols_index = {
            "contracts": set(),
            "enums": set(),
            "canonical_enums": set(),
            "errors": set(),
            "canonical_errors": set(),
            "events": set(),
            "canonical_events": set(),
            "functions": set(),
            "canonical_functions": set(),
            "modifiers": set(),
            "canonical_modifiers": set(),
            "structs": set(),
            "canonical_structs": set(),
            "user_defined_value_types": set(),
            "canonical_user_defined_value_types": set(),
            "variables": set(),
            "canonical_variables": set(),
        }

        with ctx_manager:
            successful_compilation_units = []
            all_errored_files: Set[Path] = set()

            for cu, solc_output in zip(compilation_units, ret):
                errored_files: Set[Path] = set()
                errors_per_cu[cu.hash] = set()

                for error in solc_output.errors:
                    errors_per_cu[cu.hash].add(error)
                    if error.severity == SolcOutputErrorSeverityEnum.ERROR:
                        if error.source_location is not None:
                            path = cu.source_unit_name_to_path(
                                error.source_location.file
                            )
                            errored_files.add(path)
                        else:
                            # whole compilation unit errored
                            errored_files |= cu.files

                self._out_edge_bfs(cu, errored_files, errored_files)
                all_errored_files |= errored_files

                for file in errored_files:
                    if file in build.source_units:
                        build.reference_resolver.run_destroy_callbacks(file)
                        build._source_units.pop(file)
                    if file in build.interval_trees:
                        build._interval_trees.pop(file)

                if len(errored_files) == 0:
                    successful_compilation_units.append((cu, solc_output))

            # files_to_compile and files importing them
            files_to_recompile = set(
                graph.nodes[n[1]]["path"]  # pyright: ignore reportGeneralTypeIssues
                for n in nx.edge_bfs(
                    graph,
                    [
                        source_unit_name
                        for source_unit_name in graph.nodes  # pyright: ignore reportGeneralTypeIssues
                        if graph.nodes[source_unit_name]["path"]
                        in files_to_compile  # pyright: ignore reportGeneralTypeIssues
                    ],
                )
            ) | set(files_to_compile)

            # destroy callbacks for IR nodes that will be replaced by new ones must be executed before
            # new IR nodes are created
            for file in files_to_recompile:
                if file in build.source_units:
                    build.reference_resolver.run_destroy_callbacks(file)
                    build._source_units.pop(file)
                if file in build.interval_trees:
                    build._interval_trees.pop(file)

            # clear indexed node types responsible for handling multiple structurally different ASTs for the same file
            build.reference_resolver.clear_indexed_nodes(files_to_recompile)

            source_units_info = {
                str(source_unit): SourceUnitInfo(
                    graph.nodes[source_unit]["path"], graph.nodes[source_unit]["hash"]
                )
                for source_unit in graph.nodes
                if graph.nodes[source_unit]["path"] not in deleted_files
                and graph.nodes[source_unit]["path"] not in all_errored_files
                and graph.nodes[source_unit]["path"] not in files_to_recompile
            }

            processed_files: Set[Path] = set()
            for cu, solc_output in successful_compilation_units:
                # files requested to be compiled and files that import these files (even indirectly)
                recompiled_files: Set[Path] = set()
                self._out_edge_bfs(cu, files_to_compile & cu.files, recompiled_files)

                for source_unit_name, raw_ast in solc_output.sources.items():
                    source_units_info[source_unit_name] = SourceUnitInfo(
                        graph.nodes[source_unit_name]["path"],
                        graph.nodes[source_unit_name]["hash"],
                    )

                    path = cu.source_unit_name_to_path(source_unit_name)
                    ast = AstSolc.parse_obj(raw_ast.ast)

                    build.reference_resolver.register_source_file_id(
                        raw_ast.id, path, cu.hash
                    )
                    build.reference_resolver.index_nodes(ast, path, cu.hash)

                    if (
                        path in build.source_units and path not in recompiled_files
                    ) or path in processed_files:
                        continue
                    processed_files.add(path)
                    assert (
                        source_unit_name in graph.nodes
                    ), f"Source unit {source_unit_name} not in graph"

                    interval_tree = IntervalTree()
                    init = IrInitTuple(
                        path,
                        graph.nodes[source_unit_name]["content"],
                        cu,
                        interval_tree,
                        build.reference_resolver,
                        solc_output.contracts[source_unit_name]
                        if source_unit_name in solc_output.contracts
                        else None,
                    )
                    build._source_units[path] = SourceUnit(init, ast)
                    build._interval_trees[path] = interval_tree

                build.reference_resolver.run_post_process_callbacks(
                    CallbackParams(
                        interval_trees=build.interval_trees,
                        source_units=build.source_units,
                    )
                )

            if write_artifacts:
                for source_unit in build._source_units.values():
                    for declaration in source_unit.declarations_iter():
                        if isinstance(declaration, ContractDefinition):
                            symbols_index["contracts"].add(declaration.name)
                        elif isinstance(declaration, EnumDefinition):
                            symbols_index["enums"].add(declaration.name)
                            symbols_index["canonical_enums"].add(
                                declaration.canonical_name
                            )
                        elif isinstance(declaration, ErrorDefinition):
                            symbols_index["errors"].add(declaration.name)
                            symbols_index["canonical_errors"].add(
                                declaration.canonical_name
                            )
                        elif isinstance(declaration, EventDefinition):
                            symbols_index["events"].add(declaration.name)
                            symbols_index["canonical_events"].add(
                                declaration.canonical_name
                            )
                        elif isinstance(declaration, FunctionDefinition):
                            symbols_index["functions"].add(declaration.name)
                            symbols_index["canonical_functions"].add(
                                declaration.canonical_name
                            )
                        elif isinstance(declaration, ModifierDefinition):
                            symbols_index["modifiers"].add(declaration.name)
                            symbols_index["canonical_modifiers"].add(
                                declaration.canonical_name
                            )
                        elif isinstance(declaration, StructDefinition):
                            symbols_index["structs"].add(declaration.name)
                            symbols_index["canonical_structs"].add(
                                declaration.canonical_name
                            )
                        elif isinstance(declaration, UserDefinedValueTypeDefinition):
                            symbols_index["user_defined_value_types"].add(
                                declaration.name
                            )
                            symbols_index["canonical_user_defined_value_types"].add(
                                declaration.canonical_name
                            )
                        elif isinstance(declaration, VariableDeclaration):
                            symbols_index["variables"].add(declaration.name)
                            symbols_index["canonical_variables"].add(
                                declaration.canonical_name
                            )

        if console is not None:
            end = time.perf_counter()
            console.log(
                f"[green]Processed compilation results in [bold green]{end - start:.2f} s[/bold green][/]"
            )

        self._latest_build_info = ProjectBuildInfo(
            compilation_units={
                cu_hash.hex(): CompilationUnitBuildInfo(errors=list(errors))
                for cu_hash, errors in errors_per_cu.items()
            },
            allow_paths=self.__config.compiler.solc.allow_paths,
            exclude_paths=self.__config.compiler.solc.exclude_paths,
            include_paths=self.__config.compiler.solc.include_paths,
            settings=build_settings,
            source_units_info=source_units_info,
            target_solidity_version=self.__config.compiler.solc.target_version,
            wake_version=get_package_version("eth-wake"),
            incremental=incremental,
        )
        self._latest_build = build

        if write_artifacts and (
            len(compilation_units) > 0 or len(deleted_files) > 0 or force_recompile
        ):
            logger.debug("Writing artifacts")
            self.write_artifacts(console=console)

            self.__config.project_root_path.joinpath(
                ".wake/build/symbols.json"
            ).write_text(
                json.dumps(
                    symbols_index,
                    default=lambda x: list(x) if isinstance(x, set) else x,
                )
            )

        errors = set()
        for error_list in errors_per_cu.values():
            errors |= error_list

        logger.debug(f"Compilation finished with {len(errors)} errors")

        wake_comments: KeyedDefaultDict[
            str,  # pyright: ignore reportGeneralTypeIssues
            Dict[str, Dict[int, WakeComment]],
        ] = KeyedDefaultDict(
            lambda source_unit_name: self._latest_graph.nodes[  # pyright: ignore reportGeneralTypeIssues
                source_unit_name
            ][
                "wake_comments"
            ]
        )

        if console is not None:
            for error in errors:
                if (
                    error.severity != SolcOutputErrorSeverityEnum.ERROR
                    and error.source_location is not None
                ):
                    source_unit_name = error.source_location.file
                    path = self._latest_source_units_to_paths[source_unit_name]
                    content = self._latest_graph.nodes[source_unit_name]["content"]

                    if error_commented_out(
                        error.error_code,
                        self._get_line_from_offset(
                            path, error.source_location.start, content
                        ),
                        self._get_line_from_offset(
                            path, error.source_location.end, content
                        ),
                        wake_comments[source_unit_name],
                    ):
                        continue

                if (
                    error.severity == SolcOutputErrorSeverityEnum.ERROR
                    or not no_warnings
                ):
                    if error.formatted_message is not None:
                        console.print(
                            rich.panel.Panel(error.formatted_message, highlight=True)
                        )
                    else:
                        console.print(rich.panel.Panel(error.message, highlight=True))

        return build, errors

    def write_artifacts(
        self, *, console: Optional[rich.console.Console] = None
    ) -> None:
        if self._latest_build_info is None or self._latest_build is None:
            raise Exception("Project not compiled yet")

        ctx_manager = (
            console.status(f"[bold green]Writing build artifacts...[/]")
            if console
            else nullcontext()
        )
        start = time.perf_counter()

        build_key_path = self.__config.global_data_path / "build.key"
        build_key = b""
        if build_key_path.is_file():
            build_key = build_key_path.read_bytes()
        if len(build_key) != 64:
            build_key = os.urandom(64)
            build_key_path.write_bytes(build_key)

        with ctx_manager:
            build_path = self.__config.project_root_path / ".wake" / "build"
            build_path.mkdir(parents=True, exist_ok=True)

            with (build_path / "build.json").open("w") as f:
                f.write(self._latest_build_info.json(by_alias=True, exclude_none=True))

            with (build_path / "build.bin").open("wb") as data_file, (
                build_path / "build.bin.sig"
            ).open("wb") as sig_file:
                build_data = pickle.dumps(self._latest_build)
                h = BLAKE2b.new(digest_bits=512, key=build_key)
                h.update(build_data)

                data_file.write(build_data)
                sig_file.write(h.digest())

        if console is not None:
            end = time.perf_counter()
            console.log(
                f"[green]Wrote build artifacts in [bold green]{end - start:.2f} s[/bold green][/]"
            )

    async def compile_unit_raw(
        self,
        compilation_unit: CompilationUnit,
        target_version: SolidityVersion,
        build_settings: SolcInputSettings,
    ) -> SolcOutput:
        # Dict[source_unit_name: str, path: Path]
        files = {}
        # Dict[source_unit_name: str, content: str]
        sources = {}
        for source_unit_name, data in compilation_unit.graph.nodes.items():
            path = data["path"]
            content = data["content"]
            if content is None:
                files[source_unit_name] = path
            else:
                sources[source_unit_name] = content.decode("utf-8")

        # run the solc executable
        return await self.__solc_frontend.compile(
            files, sources, target_version, build_settings
        )
