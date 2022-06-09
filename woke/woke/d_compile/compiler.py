from itertools import chain
from typing import (
    List,
    Dict,
    Iterable,
    FrozenSet,
    Set,
    Tuple,
    Optional,
    Collection,
    Mapping,
)
from collections import deque
from pathlib import Path
import asyncio
import logging
import platform
import time

from Cryptodome.Hash import BLAKE2b
from pathvalidate import sanitize_filename  # type: ignore
import aiofiles
import networkx as nx
from pydantic import ValidationError
from rich.progress import Progress

from woke.a_config import WokeConfig
from woke.b_svm import SolcVersionManager
from woke.c_regex_parsing import SoliditySourceParser
from woke.c_regex_parsing.solidity_version import (
    SolidityVersionRanges,
    SolidityVersionRange,
    SolidityVersion,
)
from .solc_frontend import (
    SolcFrontend,
    SolcOutput,
    SolcInputSettings,
    SolcOutputSelectionEnum,
    SolcOutputSourceInfo,
    SolcOutputContractInfo,
)
from .source_unit_name_resolver import SourceUnitNameResolver
from .source_path_resolver import SourcePathResolver
from .exceptions import CompilationError
from .build_data_model import CompilationUnitBuildInfo, ProjectBuildInfo


logger = logging.getLogger(__name__)


class CompilationUnit:
    __unit_graph: nx.DiGraph
    __version_ranges: SolidityVersionRanges
    __blake2b_digest: bytes

    def __init__(self, unit_graph: nx.DiGraph, version_ranges: SolidityVersionRanges):
        self.__unit_graph = unit_graph
        self.__version_ranges = version_ranges

        sorted_nodes = sorted(
            unit_graph, key=(lambda node: unit_graph.nodes[node]["source_unit_name"])
        )
        blake2 = BLAKE2b.new(digest_bits=256)

        for node in sorted_nodes:
            blake2.update(unit_graph.nodes[node]["hash"])
        self.__blake2b_digest = blake2.digest()

    def __len__(self):
        return len(self.__unit_graph.nodes)

    def __str__(self):
        return "\n".join(str(path) for path in self.__unit_graph.nodes)

    @property
    def files(self) -> FrozenSet[Path]:
        return frozenset(self.__unit_graph.nodes)

    @property
    def source_unit_names(self) -> FrozenSet[str]:
        return frozenset(
            self.__unit_graph.nodes[node]["source_unit_name"]
            for node in self.__unit_graph.nodes
        )

    @property
    def versions(self) -> SolidityVersionRanges:
        return self.__version_ranges

    @property
    def blake2b_digest(self) -> bytes:
        return self.__blake2b_digest

    @property
    def blake2b_hexdigest(self) -> str:
        return self.blake2b_digest.hex()

    @property
    def graph(self) -> nx.DiGraph:
        return self.__unit_graph


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

    def __resolve_source_unit_names(
        self, files: Collection[Path], modified_files: Mapping[Path, str]
    ) -> nx.DiGraph:
        # source unit name, full path, file content
        source_units_queue: deque[Tuple[str, Path, Optional[str]]] = deque()
        source_units: Dict[str, Path] = {}

        # for every source file resolve a source unit name
        for file in chain(files, modified_files.keys()):
            file = file.resolve(strict=True)

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
                versions, imports, h = SoliditySourceParser.parse(path)
            else:
                versions, imports, h = SoliditySourceParser.parse_source(content)
            graph.add_node(
                path,
                source_unit_name=source_unit_name,
                versions=versions,
                hash=h,
                content=content,
            )
            source_units[source_unit_name] = path

            for _import in imports:
                import_unit_name = self.__source_unit_name_resolver.resolve_import(
                    source_unit_name, _import
                )
                import_path = self.__source_path_resolver.resolve(
                    import_unit_name
                ).resolve(strict=True)

                if import_unit_name in source_units:
                    other_path = source_units[import_unit_name]
                    if import_path != other_path:
                        raise ValueError(
                            f"Same source unit name `{import_unit_name}` for multiple source files:\n{import_path}\n{other_path}"
                        )

                if import_path not in graph.nodes:
                    source_units_queue.append((import_unit_name, import_path, None))

                graph.add_edge(import_path, path)
        return graph

    def __build_compilation_units(self, graph: nx.DiGraph) -> List[CompilationUnit]:
        sinks = [node for node, out_degree in graph.out_degree() if out_degree == 0]
        compilation_units = []

        for sink in sinks:
            compilation_unit = self.__build_compilation_unit(graph, [sink])
            compilation_units.append(compilation_unit)

        # cycles can also be "sinks" in terms of compilation units
        for cycle in nx.simple_cycles(graph):
            out_degree_sum = sum(
                out_degree for *_, out_degree in graph.out_degree(cycle)
            )

            if out_degree_sum == len(cycle):
                compilation_unit = self.__build_compilation_unit(graph, cycle)
                compilation_units.append(compilation_unit)
        return compilation_units

    def __build_compilation_unit(
        self, graph: nx.DiGraph, start: Iterable[Path]
    ) -> CompilationUnit:
        nodes_subset = set()
        nodes_queue: deque[Path] = deque()
        nodes_queue.extend(start)

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

        if len(versions) == 0:
            raise CompilationError(
                "Unable to find any solc version to compile following files:\n"
                + "\n".join(str(path) for path in nodes_subset)
            )

        subgraph = graph.subgraph(nodes_subset)
        return CompilationUnit(subgraph, versions)

    def __create_build_settings(
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
        settings.output_selection = {"*": {}}

        if SolcOutputSelectionEnum.ALL in output_types:
            settings.output_selection["*"][""] = [SolcOutputSelectionEnum.AST]  # type: ignore
            settings.output_selection["*"]["*"] = [SolcOutputSelectionEnum.ALL]  # type: ignore
        else:
            if SolcOutputSelectionEnum.AST in output_types:
                settings.output_selection["*"][""] = [SolcOutputSelectionEnum.AST]  # type: ignore
            settings.output_selection["*"]["*"] = [output_type for output_type in output_types if output_type != SolcOutputSelectionEnum.AST]  # type: ignore

        return settings

    def __write_global_artifacts(
        self,
        build_path: Path,
        build_settings: SolcInputSettings,
        output: Tuple[SolcOutput],
        compilation_units: List[CompilationUnit],
    ) -> None:
        units_info = {}

        # units are already sorted
        for index, (unit, out) in enumerate(zip(compilation_units, output)):
            sources = {}
            for source_unit_name in out.sources.keys():
                sources[source_unit_name] = (
                    Path(f"{index:03d}")
                    / "asts"
                    / sanitize_filename(source_unit_name, "_", platform="universal")
                )

            contracts = {}
            for source_unit_name, info in out.contracts.items():
                contracts[source_unit_name] = {}
                for contract in info.keys():
                    contracts[source_unit_name][contract] = (
                        Path(f"{index:03d}") / "contracts" / f"{contract}.json"
                    )

            info = CompilationUnitBuildInfo(
                build_dir=f"{index:03d}",
                sources=sources,
                contracts=contracts,
                errors=out.errors,
                source_units=sorted(unit.source_unit_names),
                allow_paths=sorted(self.__config.compiler.solc.allow_paths),
                include_paths=sorted(self.__config.compiler.solc.include_paths),
                settings=build_settings,
            )
            units_info[unit.blake2b_hexdigest] = info

        build_info = ProjectBuildInfo(compilation_units=units_info)
        with (build_path / "build.json").open("w") as f:
            f.write(build_info.json(by_alias=True, exclude_none=True))

    async def compile(
        self,
        files: Collection[Path],
        output_types: Collection[SolcOutputSelectionEnum],
        write_artifacts: bool = True,
        reuse_latest_artifacts: bool = True,
        modified_files: Optional[Mapping[Path, str]] = None,
    ) -> List[SolcOutput]:
        if modified_files is None:
            modified_files = {}
        if len(files) + len(modified_files) == 0:
            raise CompilationError("No source files provided to compile.")
        if not set(files).isdisjoint(set(modified_files.keys())):
            raise ValueError("Files and modified files must not overlap.")

        graph = self.__resolve_source_unit_names(files, modified_files)
        compilation_units = self.__build_compilation_units(graph)
        build_settings = self.__create_build_settings(output_types)

        # sort compilation units by their BLAKE2b hexdigest
        compilation_units.sort(key=lambda u: u.blake2b_hexdigest)

        if write_artifacts:
            # prepare build dir
            build_path = (
                self.__config.project_root_path / ".woke-build" / str(int(time.time()))
            )
            build_path.mkdir(parents=True, exist_ok=False)
        else:
            build_path = None

        latest_build_path = self.__config.project_root_path / ".woke-build" / "latest"
        if reuse_latest_artifacts:
            try:
                latest_build_info = ProjectBuildInfo.parse_file(
                    latest_build_path / "build.json"
                )
            except ValidationError:
                logger.warning(
                    f"Failed to parse '{latest_build_path / 'build.json'}' file while trying to reuse the latest build artifacts."
                )
                latest_build_info = None
            except FileNotFoundError as e:
                logger.warning(
                    f"Unable to find '{e.filename}' file while trying to reuse the latest build artifacts."
                )
                latest_build_info = None
        else:
            latest_build_info = None

        target_versions = []
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
                # TODO Do not use the latest matching version in Woke compiler
                target_version = next(
                    version
                    for version in reversed(self.__svm.list_all())
                    if version in compilation_unit.versions
                )
            target_versions.append(target_version)

            if not self.__svm.get_path(target_version).is_file():
                with Progress() as progress:
                    task = progress.add_task(
                        f"[green]Downloading solc {target_version}", total=1
                    )
                    await self.__svm.install(
                        target_version,
                        progress=(lambda x: progress.update(task, completed=x)),
                    )

        tasks = []
        for index, (compilation_unit, target_version) in enumerate(
            zip(compilation_units, target_versions)
        ):
            task = asyncio.create_task(
                self.__compile_unit(
                    compilation_unit,
                    target_version,
                    build_settings,
                    build_path / f"{index:03d}" if build_path is not None else None,
                    latest_build_info,
                )
            )
            tasks.append(task)

        # wait for compilation of all compilation units
        try:
            ret = await asyncio.gather(*tasks)
        except Exception:
            for task in tasks:
                task.cancel()
            raise

        if write_artifacts:
            if build_path is None:
                # should not really happen (it is present here just to silence the linter)
                raise ValueError("Build path is not set.")
            self.__write_global_artifacts(
                build_path, build_settings, ret, compilation_units
            )

            # create `latest` symlink pointing to the just created build directory
            if platform.system() != "Windows":
                if latest_build_path.is_symlink():
                    latest_build_path.unlink()
                latest_build_path.symlink_to(build_path, target_is_directory=True)

        return list(ret)

    async def __compile_unit(
        self,
        compilation_unit: CompilationUnit,
        target_version: SolidityVersion,
        build_settings: SolcInputSettings,
        build_path: Optional[Path],
        latest_build_info: Optional[ProjectBuildInfo],
    ) -> SolcOutput:
        # try to reuse the latest build artifacts
        if (
            latest_build_info is not None
            and compilation_unit.blake2b_hexdigest
            in latest_build_info.compilation_units
        ):
            latest_unit_info = latest_build_info.compilation_units[
                compilation_unit.blake2b_hexdigest
            ]

            if (
                latest_unit_info.source_units
                == sorted(compilation_unit.source_unit_names)
                and latest_unit_info.allow_paths
                == sorted(self.__config.compiler.solc.allow_paths)
                and latest_unit_info.include_paths
                == sorted(self.__config.compiler.solc.include_paths)
                and latest_unit_info.settings == build_settings
            ):
                try:
                    logger.info("Reusing the latest build artifacts.")
                    latest_build_path = (
                        self.__config.project_root_path / ".woke-build" / "latest"
                    )
                    sources = {}
                    for source, path in latest_unit_info.sources.items():
                        sources[source] = SolcOutputSourceInfo.parse_file(
                            latest_build_path / path
                        )

                    contracts = {}
                    for (
                        source_unit,
                        source_unit_info,
                    ) in latest_unit_info.contracts.items():
                        contracts[source_unit] = {}
                        for contract, path in source_unit_info.items():
                            contracts[source_unit][
                                contract
                            ] = SolcOutputContractInfo.parse_file(
                                latest_build_path / path
                            )
                    out = SolcOutput(
                        errors=latest_unit_info.errors,
                        sources=sources,
                        contracts=contracts,
                    )
                except ValidationError:
                    logger.warning(
                        "Failed to parse the latest build artifacts, falling back to solc compilation."
                    )
                    out = await self.__compile_unit_raw(
                        compilation_unit, target_version, build_settings
                    )
                except FileNotFoundError as e:
                    logger.warning(
                        f"Unable to find '{e.filename}' file while reusing the latest build info. Build artifacts may be corrupted."
                    )
                    out = await self.__compile_unit_raw(
                        compilation_unit, target_version, build_settings
                    )
            else:
                logger.info(
                    "Build settings have changed since the last build. Falling back to solc compilation."
                )
                out = await self.__compile_unit_raw(
                    compilation_unit, target_version, build_settings
                )
        else:
            out = await self.__compile_unit_raw(
                compilation_unit, target_version, build_settings
            )

        # write build artifacts
        if build_path is not None:
            build_path.mkdir(parents=False, exist_ok=False)
            await self.__write_artifacts(out, build_path)

        return out

    async def __compile_unit_raw(
        self,
        compilation_unit: CompilationUnit,
        target_version: SolidityVersion,
        build_settings: SolcInputSettings,
    ) -> SolcOutput:
        # Dict[source_unit_name: str, path: Path]
        files = {}
        # Dict[source_unit_name: str, content: str]
        sources = {}
        for node, data in compilation_unit.graph.nodes.items():
            source_unit_name = data["source_unit_name"]
            content = data["content"]
            if content is None:
                files[source_unit_name] = node
            else:
                sources[source_unit_name] = content

        # run the solc executable
        return await self.__solc_frontend.compile(
            files, sources, target_version, build_settings
        )

    @staticmethod
    async def __write_artifacts(output: SolcOutput, build_path: Path) -> None:
        if output.sources is not None:
            ast_path = build_path / "asts"
            ast_path.mkdir(parents=False, exist_ok=False)
            for source_unit_name, value in output.sources.items():
                # AST output is generated per file (source unit name)
                # Because a source unit name can contain slashes, it is not possible to name the AST build file
                # by its source unit name. Blake2b hash of the Solidity source file content is used instead.
                file_path = ast_path / sanitize_filename(
                    source_unit_name, "_", platform="universal"
                )

                if file_path.is_file():
                    raise CompilationError(
                        f"Cannot write build info into '{file_path}' - file already exists."
                    )
                async with aiofiles.open(file_path, mode="w") as f:
                    await f.write(value.json(by_alias=True, exclude_none=True))

        if output.contracts is not None:
            contract_path = build_path / "contracts"
            contract_path.mkdir(parents=False, exist_ok=False)
            for source_unit_name, d in output.contracts.items():
                # All other build info is generated per contract. Contract names cannot contain slashes so it should
                # be safe to name the build info file by its contract name.
                for contract, info in d.items():
                    file_path = contract_path / (contract + ".json")

                    async with aiofiles.open(file_path, mode="w") as f:
                        await f.write(info.json(by_alias=True, exclude_none=True))
