import asyncio
import logging
import pickle
from collections import defaultdict, deque
from json import JSONDecodeError
from pathlib import Path, PurePath
from typing import (
    Collection,
    DefaultDict,
    Deque,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Set,
    Tuple,
)

import networkx as nx
from intervaltree import IntervalTree
from pathvalidate import sanitize_filename  # type: ignore
from pydantic import ValidationError
from rich.progress import Progress

from woke.config import WokeConfig
from woke.core.solidity_version import (
    SolidityVersion,
    SolidityVersionRange,
    SolidityVersionRanges,
)
from woke.regex_parsing import SoliditySourceParser
from woke.svm import SolcVersionManager

from ..ast.ir.meta.source_unit import SourceUnit
from ..ast.ir.reference_resolver import CallbackParams, ReferenceResolver
from ..ast.ir.utils import IrInitTuple
from ..ast.nodes import AstSolc
from ..utils import get_package_version
from .build_data_model import BuildInfo, CompilationUnitBuildInfo, ProjectBuildInfo
from .compilation_unit import CompilationUnit
from .exceptions import CompilationError, CompilationResolveError
from .solc_frontend import (
    SolcFrontend,
    SolcInputOptimizerSettings,
    SolcInputSettings,
    SolcOutput,
    SolcOutputError,
    SolcOutputErrorSeverityEnum,
    SolcOutputSelectionEnum,
)
from .source_path_resolver import SourcePathResolver
from .source_unit_name_resolver import SourceUnitNameResolver

logger = logging.getLogger(__name__)


class SolidityCompiler:
    __config: WokeConfig
    __svm: SolcVersionManager
    __solc_frontend: SolcFrontend
    __source_unit_name_resolver: SourceUnitNameResolver
    __source_path_resolver: SourcePathResolver

    def __init__(self, woke_config: WokeConfig):
        self.__config = woke_config
        self.__svm = SolcVersionManager(woke_config)
        self.__solc_frontend = SolcFrontend(woke_config)
        self.__source_unit_name_resolver = SourceUnitNameResolver(woke_config)
        self.__source_path_resolver = SourcePathResolver(woke_config)

    def build_graph(
        self,
        files: Collection[Path],
        modified_files: Mapping[Path, str],
        ignore_errors: bool = False,
    ) -> Tuple[nx.DiGraph, Dict[PurePath, Path]]:
        # source unit name, full path, file content
        source_units_queue: deque[Tuple[PurePath, Path, Optional[str]]] = deque()
        source_units: Dict[PurePath, Path] = {}

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
                    versions, imports, h, content = SoliditySourceParser.parse(
                        path, ignore_errors
                    )
                except UnicodeDecodeError:
                    continue
            else:
                versions, imports, h = SoliditySourceParser.parse_source(
                    content, ignore_errors
                )
            graph.add_node(
                source_unit_name,
                path=path,
                versions=versions,
                hash=h,
                content=content,
                unresolved_imports=set(),
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
            graph: nx.DiGraph, start: Iterable[PurePath]
        ) -> CompilationUnit:
            nodes_subset = set()
            nodes_queue: deque[PurePath] = deque(start)
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
        for cycle in nx.simple_cycles(graph):
            out_degree_sum = sum(
                out_degree for *_, out_degree in graph.out_degree(cycle)
            )

            if out_degree_sum == len(cycle):
                compilation_unit = __build_compilation_unit(graph, cycle)
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

    async def install_solc(self, versions: Iterable[SolidityVersion]) -> None:
        for version in set(versions):
            if not self.__svm.installed(version):
                with Progress() as progress:
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
        processed: Set[PurePath] = set()
        for path in start:
            processed.update(cu.path_to_source_unit_names(path))
        out.update(start)

        queue: Deque[PurePath] = deque(processed)
        while len(queue):
            node = queue.pop()
            for out_edge in cu.graph.out_edges(node):
                from_, to = out_edge
                if to not in processed:
                    processed.add(to)
                    queue.append(to)
                    out.add(cu.source_unit_name_to_path(to))

    async def compile(
        self,
        files: Collection[Path],
        output_types: Collection[SolcOutputSelectionEnum],
        write_artifacts: bool = True,
        reuse_latest_artifacts: bool = True,
        modified_files: Optional[Mapping[Path, str]] = None,
    ) -> Tuple[BuildInfo, Set[SolcOutputError]]:
        if modified_files is None:
            modified_files = {}
        if len(files) + len(modified_files) == 0:
            raise CompilationError("No source files provided to compile.")
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

        graph, source_units_to_paths = self.build_graph(files, modified_files)
        compilation_units = self.build_compilation_units_maximize(graph)
        build_settings = self.create_build_settings(output_types)

        deleted_files: Set[Path] = set()
        errors_per_cu: DefaultDict[bytes, Set[SolcOutputError]] = defaultdict(set)

        if not reuse_latest_artifacts:
            build = BuildInfo(
                interval_trees={},
                reference_resolver=ReferenceResolver(),
                source_units={},
            )
            files_to_compile = set(
                source_units_to_paths[source_unit] for source_unit in graph.nodes
            )
            logger.debug("Not reusing latest artifacts")
        else:
            latest_build_path = self.__config.project_root_path / ".woke-build"
            try:
                build_info = ProjectBuildInfo.parse_file(
                    latest_build_path / "build.json"
                )
                source_units_blake2b: Dict[PurePath, bytes] = {
                    PurePath(source_unit_name): build_info.source_units_blake2b[
                        source_unit_name
                    ]
                    for source_unit_name in build_info.source_units_blake2b.keys()
                }

                if (
                    build_info.allow_paths != self.__config.compiler.solc.allow_paths
                    or build_info.include_paths
                    != self.__config.compiler.solc.include_paths
                    or build_info.settings != build_settings
                    or build_info.target_solidity_version
                    != self.__config.compiler.solc.target_version
                    or build_info.woke_version != get_package_version("woke")
                ):
                    # trigger the except block
                    raise CompilationError("Build settings changed")

                build = pickle.load((latest_build_path / "build.bin").open("rb"))

                # files_to_compile = modified files + force compile files (build settings changed)
                files_to_compile = set(modified_files.keys())

                for source_unit in graph.nodes:
                    if (
                        source_unit not in source_units_blake2b
                        or source_units_blake2b[source_unit]
                        != graph.nodes[source_unit]["hash"]
                    ):
                        files_to_compile.add(source_units_to_paths[source_unit])

                for source_unit in source_units_blake2b.keys():
                    if source_unit not in graph.nodes:
                        deleted_files.add(source_units_to_paths[source_unit])

                for cu_hash, cu_data in build_info.compilation_units.items():
                    if any(cu.hash.hex() == cu_hash for cu in compilation_units):
                        errors_per_cu[bytes.fromhex(cu_hash)] = set(cu_data.errors)

                # select only compilation units that need to be compiled
                compilation_units = [
                    cu for cu in compilation_units if (cu.files & files_to_compile)
                ]
                logger.debug("Reusing latest artifacts")
            except (
                CompilationError,
                ValidationError,
                JSONDecodeError,
                FileNotFoundError,
                pickle.UnpicklingError,
            ):
                build = BuildInfo(
                    interval_trees={},
                    reference_resolver=ReferenceResolver(),
                    source_units={},
                )
                files_to_compile = set(
                    source_units_to_paths[source_unit] for source_unit in graph.nodes
                )
                logger.debug("Reusing latest artifacts failed")

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

            compilation_units = merged_compilation_units

        target_versions = self.determine_solc_versions(compilation_units)
        await self.install_solc(target_versions)

        tasks = []
        for compilation_unit, target_version in zip(compilation_units, target_versions):
            task = asyncio.create_task(
                self.compile_unit_raw(compilation_unit, target_version, build_settings)
            )
            tasks.append(task)

        logger.debug(f"Compiling {len(compilation_units)} compilation units")

        # wait for compilation of all compilation units
        try:
            ret: Tuple[SolcOutput, ...] = await asyncio.gather(
                *tasks
            )  # pyright: ignore[reportGeneralTypeIssues]
        except Exception:
            for task in tasks:
                task.cancel()
            raise

        for deleted_file in deleted_files:
            if deleted_file in build.source_units:
                build.reference_resolver.run_destroy_callbacks(deleted_file)
                build.source_units.pop(deleted_file)

        processed_files: Set[Path] = set()

        for cu, solc_output in zip(compilation_units, ret):
            errored: bool = False
            errors_per_cu[cu.hash] = set()

            for error in solc_output.errors:
                errors_per_cu[cu.hash].add(error)
                if error.severity == SolcOutputErrorSeverityEnum.ERROR:
                    errored = True

            # files requested to be compiled and files that import these files (even indirectly)
            recompiled_files: Set[Path] = set()
            self._out_edge_bfs(cu, files_to_compile & cu.files, recompiled_files)

            if not errored:
                for source_unit_name, raw_ast in solc_output.sources.items():
                    source_unit = PurePath(source_unit_name)
                    path = cu.source_unit_name_to_path(source_unit)
                    ast = AstSolc.parse_obj(raw_ast.ast)

                    build.reference_resolver.index_nodes(ast, path, cu.hash)

                    if (
                        path in build.source_units and path not in recompiled_files
                    ) or path in processed_files:
                        continue
                    processed_files.add(path)
                    assert (
                        source_unit in graph.nodes
                    ), f"Source unit {source_unit} not in graph"

                    interval_tree = IntervalTree()
                    init = IrInitTuple(
                        path,
                        graph.nodes[source_unit]["content"].encode("utf-8"),
                        cu,
                        interval_tree,
                        build.reference_resolver,
                        solc_output.contracts[source_unit_name]
                        if source_unit_name in solc_output.contracts
                        else None,
                    )
                    build.reference_resolver.run_destroy_callbacks(path)
                    build.source_units[path] = SourceUnit(init, ast)
                    build.interval_trees[path] = interval_tree

                build.reference_resolver.run_post_process_callbacks(
                    CallbackParams(
                        interval_trees=build.interval_trees,
                        source_units=build.source_units,
                    )
                )

        if write_artifacts and (len(compilation_units) > 0 or len(deleted_files) > 0):
            logger.debug("Writing artifacts")
            self._write_artifacts(build, build_settings, graph, errors_per_cu)

        errors = set()
        for error_list in errors_per_cu.values():
            errors |= error_list

        return build, errors

    def _write_artifacts(
        self,
        build: BuildInfo,
        build_settings: SolcInputSettings,
        graph: nx.DiGraph,
        errors_per_cu: Dict[bytes, Set[SolcOutputError]],
    ) -> None:
        build_path = self.__config.project_root_path / ".woke-build"
        build_path.mkdir(exist_ok=True)

        build_info = ProjectBuildInfo(
            compilation_units={
                cu_hash.hex(): CompilationUnitBuildInfo(errors=list(errors))
                for cu_hash, errors in errors_per_cu.items()
            },
            allow_paths=self.__config.compiler.solc.allow_paths,
            include_paths=self.__config.compiler.solc.include_paths,
            settings=build_settings,
            source_units_blake2b={
                str(source_unit): graph.nodes[source_unit]["hash"]
                for source_unit in graph.nodes
            },
            target_solidity_version=self.__config.compiler.solc.target_version,
            woke_version=get_package_version("woke"),
        )
        with (build_path / "build.json").open("w") as f:
            f.write(build_info.json(by_alias=True, exclude_none=True))

        with (build_path / "build.bin").open("wb") as f:
            pickle.dump(build, f)

    async def compile_unit_raw(
        self,
        compilation_unit: CompilationUnit,
        target_version: SolidityVersion,
        build_settings: SolcInputSettings,
    ) -> SolcOutput:
        # Dict[source_unit_name: PurePath, path: Path]
        files = {}
        # Dict[source_unit_name: PurePath, content: str]
        sources = {}
        for source_unit_name, data in compilation_unit.graph.nodes.items():
            path = data["path"]
            content = data["content"]
            if content is None:
                files[source_unit_name] = path
            else:
                sources[source_unit_name] = content

        # run the solc executable
        return await self.__solc_frontend.compile(
            files, sources, target_version, build_settings
        )
