import asyncio
import logging
import platform
import shutil
import time
from collections import deque
from itertools import chain
from pathlib import Path, PurePath
from typing import Collection, Dict, Iterable, List, Mapping, Optional, Set, Tuple

import aiofiles
import networkx as nx
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

from .build_data_model import CompilationUnitBuildInfo, ProjectBuildInfo
from .compilation_unit import CompilationUnit
from .exceptions import CompilationError, CompilationResolveError
from .solc_frontend import (
    SolcFrontend,
    SolcInputSettings,
    SolcOutput,
    SolcOutputContractInfo,
    SolcOutputSelectionEnum,
    SolcOutputSourceInfo,
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
    ) -> nx.DiGraph:
        # source unit name, full path, file content
        source_units_queue: deque[Tuple[PurePath, Path, Optional[str]]] = deque()
        source_units: Dict[PurePath, Path] = {}

        # for every source file resolve a source unit name
        for file in files:
            try:
                file = file.resolve(strict=True)
            except FileNotFoundError:
                if ignore_errors:
                    continue
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
                versions, imports, h = SoliditySourceParser.parse(path, ignore_errors)
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
                        import_unit_name
                    ).resolve(strict=True)
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
        return graph

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

    @staticmethod
    def build_compilation_units_minimize(graph: nx.DiGraph) -> List[CompilationUnit]:
        """
        Builds a list of compilation units from a graph. Number of compilation units is *almost* minimized.
        This approach assures that every compiled file is in exactly one compilation unit.
        In very rare cases the project may not be possible to compile using this method. An example:
        - Lib.sol requires solc v0.5.*
        - A.sol requires solc v0.5.0 and imports Lib.sol
        - B.sol requires solc v0.5.1 and imports Lib.sol
        """
        compilation_units = []
        for component in nx.weakly_connected_components(graph):
            subgraph = graph.subgraph(component)

            versions: SolidityVersionRanges = SolidityVersionRanges(
                [SolidityVersionRange(None, None, None, None)]
            )
            for file in component:
                versions &= graph.nodes[file]["versions"]
            compilation_units.append(CompilationUnit(subgraph, versions))
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
        output: Tuple[SolcOutput, ...],
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
                    / sanitize_filename(
                        source_unit_name + ".json", "_", platform="universal"
                    )
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
                source_units=sorted(
                    str(source_unit_name) for source_unit_name in unit.source_unit_names
                ),
                allow_paths=sorted(self.__config.compiler.solc.allow_paths),
                include_paths=sorted(self.__config.compiler.solc.include_paths),
                settings=build_settings,
            )
            units_info[unit.hash.hex()] = info

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
        maximize_compilation_units: bool = False,
    ) -> List[Tuple[CompilationUnit, SolcOutput]]:
        if modified_files is None:
            modified_files = {}
        if len(files) + len(modified_files) == 0:
            raise CompilationError("No source files provided to compile.")

        graph = self.build_graph(files, modified_files)
        if maximize_compilation_units:
            compilation_units = self.build_compilation_units_maximize(graph)
        else:
            compilation_units = self.build_compilation_units_minimize(graph)
        build_settings = self.create_build_settings(output_types)

        # sort compilation units by their hash
        compilation_units.sort(key=lambda u: u.hash.hex())

        if write_artifacts:
            # prepare build dir
            build_path = self.__config.project_root_path / ".woke-build"
            if not build_path.is_dir():
                build_path.mkdir(parents=True, exist_ok=False)
            tmp_path = build_path / "tmp"
            if tmp_path.is_file():
                tmp_path.unlink()
            elif tmp_path.is_dir():
                shutil.rmtree(tmp_path)
        else:
            build_path = None

        latest_build_path = self.__config.project_root_path / ".woke-build"
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

                    async def on_progress(downloaded: int, total: int) -> None:
                        progress.update(task, completed=downloaded, total=total)  # type: ignore

                    await self.__svm.install(
                        target_version,
                        progress=on_progress,
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
            self.__rename_and_remove_artifacts(build_path)
            self.__write_global_artifacts(
                build_path, build_settings, ret, compilation_units  # type: ignore
            )

        return [(cu, out) for cu, out in zip(compilation_units, ret)]

    @staticmethod
    def __rename_and_remove_artifacts(build_path: Path):
        """
        When this func is called .woke-build/ should the following contents:
          .woke-build/old-artifact-0,...,.woke-build/old-artifact-n      <- old artifacts
          .woke-build/tmp                                                <- tmp_dir with new artifacts
          .woke-build/build.json                                         <- old build info
        This func manages removal of the old artifacts and also moves the new ones out
        of the tmp/ directory.
        This is neccesary because old artifacts can't be removed before new ones are
        created and because we want to limit the amount of stored artifacts.
        """
        for fl in build_path.iterdir():
            if fl.stem != "tmp" and fl.stem != "build.json":
                if fl.is_dir():
                    shutil.rmtree(fl)
                else:
                    fl.unlink()
        if not (build_path / "tmp").exists():
            raise ValueError("New artificats do not exist.")
        for fl in (build_path / "tmp").iterdir():
            p = Path(fl).absolute()
            parent_dir = p.parents[1]
            p.rename(parent_dir / p.name)
        (build_path / "tmp").rmdir()

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
            and compilation_unit.hash.hex() in latest_build_info.compilation_units
        ):
            latest_unit_info = latest_build_info.compilation_units[
                compilation_unit.hash.hex()
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
                    latest_build_path = self.__config.project_root_path / ".woke-build"
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
                    out = await self.compile_unit_raw(
                        compilation_unit, target_version, build_settings
                    )
                except FileNotFoundError as e:
                    logger.warning(
                        f"Unable to find '{e.filename}' file while reusing the latest build info. Build artifacts may be corrupted."
                    )
                    out = await self.compile_unit_raw(
                        compilation_unit, target_version, build_settings
                    )
            else:
                logger.info(
                    "Build settings have changed since the last build. Falling back to solc compilation."
                )
                out = await self.compile_unit_raw(
                    compilation_unit, target_version, build_settings
                )
        else:
            out = await self.compile_unit_raw(
                compilation_unit, target_version, build_settings
            )

        # write build artifacts
        if build_path is not None:
            tmp_path = build_path.parent / "tmp" / build_path.stem
            tmp_path.mkdir(parents=True, exist_ok=False)
            await self.__write_artifacts(out, tmp_path)

        return out

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
                    source_unit_name + ".json", "_", platform="universal"
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
