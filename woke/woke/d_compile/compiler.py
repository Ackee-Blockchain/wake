from typing import List, Dict, Iterable, FrozenSet, Set, Tuple, Optional, Collection
from collections import deque
from pathlib import Path
import asyncio
import json
import time

from Cryptodome.Hash import BLAKE2b
import aiofiles
import networkx as nx

from woke.a_config import WokeConfig
from woke.b_svm import SolcVersionManager
from woke.c_regex_parsing import SoliditySourceParser
from woke.c_regex_parsing.a_version import (
    SolidityVersionRanges,
    SolidityVersionRange,
    SolidityVersion,
)
from .solc_frontend import (
    SolcFrontend,
    SolcOutput,
    SolcInputSettings,
    SolcOutputSelectionEnum,
)
from .source_unit_name_resolver import SourceUnitNameResolver
from .source_path_resolver import SourcePathResolver
from .exceptions import CompilationError


class CompilationUnit:
    __unit_graph: nx.DiGraph
    __version_ranges: SolidityVersionRanges
    __blake2b_digest: bytes

    def __init__(self, unit_graph: nx.DiGraph, version_ranges: SolidityVersionRanges):
        self.__unit_graph = unit_graph
        self.__version_ranges = version_ranges

        blake2 = BLAKE2b.new(digest_bits=128)
        paths: List[Path] = list(unit_graph.nodes)
        paths.sort()
        for path in paths:
            blake2.update(unit_graph.nodes[path]["hash"])
        self.__blake2b_digest = blake2.digest()

    def __len__(self):
        return len(self.__unit_graph.nodes)

    def __str__(self):
        return "\n".join(str(path) for path in self.__unit_graph.nodes)

    @property
    def files(self) -> FrozenSet[Path]:
        return frozenset(self.__unit_graph.nodes)

    @property
    def versions(self) -> SolidityVersionRanges:
        return self.__version_ranges

    @property
    def blake2b_digest(self) -> bytes:
        return self.__blake2b_digest

    @property
    def blake2b_hexdigest(self) -> str:
        return self.blake2b_digest.hex()


class SolidityCompiler:
    __config: WokeConfig
    __svm: SolcVersionManager
    __solc_frontend: SolcFrontend
    __source_unit_name_resolver: SourceUnitNameResolver
    __source_path_resolver: SourcePathResolver
    __files: Set[Path]
    __files_graph: nx.DiGraph
    __source_units: Dict[str, Path]
    __compilation_units: List[CompilationUnit]

    def __init__(self, woke_config: WokeConfig, files: Iterable[Path]):
        self.__config = woke_config
        self.__svm = SolcVersionManager(woke_config)
        self.__solc_frontend = SolcFrontend(woke_config)
        self.__source_unit_name_resolver = SourceUnitNameResolver(woke_config)
        self.__source_path_resolver = SourcePathResolver(woke_config)
        self.__files = set()

        # deduplicate source files
        for file in files:
            resolved = file.resolve(strict=True)
            self.__files.add(resolved)

        self.__files_graph = nx.DiGraph()
        self.__source_units = dict()
        self.__compilation_units = []

    def __resolve_source_unit_names(self) -> None:
        source_units_queue: deque[Tuple[str, Path]] = deque()

        # for every source file resolve a source unit name
        for file in self.__files:
            source_unit_name = self.__source_unit_name_resolver.resolve_cmdline_arg(
                str(file)
            )
            if source_unit_name in self.__source_units:
                first = str(self.__source_units[source_unit_name])
                second = str(file)
                raise CompilationError(
                    f"Same source unit name `{source_unit_name}` for multiple source files:\n{first}\n{second}"
                )

            source_units_queue.append((source_unit_name, file))

        # recursively process all sources
        while len(source_units_queue) > 0:
            source_unit_name, path = source_units_queue.pop()
            versions, imports, h = SoliditySourceParser.parse(path)
            self.__files_graph.add_node(
                path, source_unit_name=source_unit_name, versions=versions, hash=h
            )
            self.__source_units[source_unit_name] = path

            for _import in imports:
                import_unit_name = self.__source_unit_name_resolver.resolve_import(
                    source_unit_name, _import
                )
                import_path = self.__source_path_resolver.resolve(
                    import_unit_name
                ).resolve(strict=True)

                if import_unit_name in self.__source_units:
                    other_path = self.__source_units[import_unit_name]
                    if import_path != other_path:
                        raise ValueError(
                            f"Same source unit name `{import_unit_name}` for multiple source files:\n{import_path}\n{other_path}"
                        )

                if import_path not in self.__files_graph.nodes:
                    source_units_queue.append((import_unit_name, import_path))

                self.__files_graph.add_edge(import_path, path)

    def __build_compilation_units(self) -> None:
        sinks = [
            node
            for node, out_degree in self.__files_graph.out_degree()
            if out_degree == 0
        ]

        for sink in sinks:
            compilation_unit = self.__build_compilation_unit([sink])
            self.__compilation_units.append(compilation_unit)

        # cycles can also be "sinks" in terms of compilation units
        for cycle in nx.simple_cycles(self.__files_graph):
            out_degree_sum = sum(
                out_degree for *_, out_degree in self.__files_graph.out_degree(cycle)
            )

            if out_degree_sum == len(cycle):
                compilation_unit = self.__build_compilation_unit(cycle)
                self.__compilation_units.append(compilation_unit)

    def __build_compilation_unit(self, start: Iterable[Path]) -> CompilationUnit:
        nodes_subset = set()
        nodes_queue: deque[Path] = deque()
        nodes_queue.extend(start)

        versions: SolidityVersionRanges = SolidityVersionRanges(
            [SolidityVersionRange(None, None, None, None)]
        )

        while len(nodes_queue) > 0:
            node = nodes_queue.pop()
            versions &= self.__files_graph.nodes[node]["versions"]

            if node in nodes_subset:
                continue
            nodes_subset.add(node)

            for in_edge in self.__files_graph.in_edges(node):
                _from, to = in_edge
                if _from not in nodes_subset:
                    nodes_queue.append(_from)

        if len(versions) == 0:
            raise CompilationError(
                "Unable to find any solc version to compile following files:\n"
                + "\n".join(str(path) for path in nodes_subset)
            )

        subgraph = self.__files_graph.subgraph(nodes_subset)
        return CompilationUnit(subgraph, versions)

    def __create_build_settings(
        self, output_types: Collection[SolcOutputSelectionEnum]
    ) -> SolcInputSettings:
        settings = SolcInputSettings()  # type: ignore
        # TODO Allow to set all solc build settings
        # Currently it is not possible to set all solc standard JSON input build settings.
        # These include: stopAfter, optimizer, via_IR, debug, metadata, libraries and model checker settings.
        # See https://docs.soliditylang.org/en/v0.8.12/using-the-compiler.html#input-description.
        # Also it is not possible to specify solc output per contract or per source file.
        settings.remappings = self.__config.compiler.solc.remappings
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

    async def compile(
        self,
        output_types: Collection[SolcOutputSelectionEnum],
        write_artifacts: bool = True,
    ) -> None:
        if len(self.__files) == 0:
            raise CompilationError("No source files provided to compile.")

        self.__resolve_source_unit_names()
        self.__build_compilation_units()
        build_settings = self.__create_build_settings(output_types)

        if write_artifacts:
            # prepare build dir
            build_path = (
                self.__config.project_root_path / ".woke-build" / str(int(time.time()))
            )
            build_path.mkdir(parents=True, exist_ok=False)
        else:
            build_path = None

        target_version = self.__config.compiler.solc.target_version
        tasks = []
        for compilation_unit in self.__compilation_units:
            task = asyncio.create_task(
                self.__compile_unit(
                    compilation_unit, target_version, build_settings, build_path
                )
            )
            tasks.append(task)

        # wait for compilation of all compilation units
        for task in asyncio.as_completed(tasks):
            await task

        if write_artifacts:
            # create `latest` symlink to the just created build directory
            latest_build_path = (
                self.__config.project_root_path / ".woke-build" / "latest"
            )
            if latest_build_path.is_symlink():
                latest_build_path.unlink()
            latest_build_path.symlink_to(build_path, target_is_directory=True)

    async def __compile_unit(
        self,
        compilation_unit: CompilationUnit,
        target_version: SolidityVersion,
        build_settings: SolcInputSettings,
        build_path: Optional[Path],
    ) -> None:
        # Dict[source_unit_name: str, path: Path]
        files = {}
        for file in compilation_unit.files:
            source_unit_name = self.__files_graph.nodes[file]["source_unit_name"]
            files[source_unit_name] = file

        if target_version is not None:
            if target_version not in compilation_unit.versions:
                files_str = "\n".join(str(path) for path in compilation_unit.files)
                raise CompilationError(
                    f"Unable to compile following files with solc version {target_version} set in config files:\n"
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

        # run the solc executable
        out = await self.__solc_frontend.compile_files(
            files, target_version, build_settings
        )

        # write build artifacts
        if build_path is not None:
            build_path = build_path / compilation_unit.blake2b_hexdigest
            build_path.mkdir(parents=False, exist_ok=False)
            await self.__write_artifacts(out, build_path)

    async def __write_artifacts(self, output: SolcOutput, build_path: Path) -> None:
        if output.sources is not None:
            for source_unit_name, value in output.sources.items():
                # AST output is generated per file (source unit name)
                # Because a source unit name can contain slashes, it is not possible to name the AST build file
                # by its source unit name. Blake2b hash of the Solidity source file content is used instead.
                path = self.__source_units[source_unit_name]
                ast_path = build_path / self.__files_graph.nodes[path]["hash"].hex()

                async with aiofiles.open(ast_path, mode="w") as f:
                    await f.write(json.dumps(value.ast))

        if output.contracts is not None:
            for source_unit_name, d in output.contracts.items():
                # All other build info is generated per contract. Contract names cannot contain slashes so it should
                # be safe to name the build info file by its contract name.
                for contract, info in d.items():
                    info_path = build_path / (contract + ".json")

                    async with aiofiles.open(info_path, mode="w") as f:
                        await f.write(info.json(by_alias=True, exclude_none=True))
