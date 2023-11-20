import logging
import os
import platform
import reprlib
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, FrozenSet, Iterable, Optional, Set, Tuple, Union

import networkx as nx
import tomli

from woke.core import get_logger
from woke.utils import change_cwd

from ..core.solidity_version import SolidityVersion
from .data_model import (
    CompilerConfig,
    DeploymentConfig,
    DetectorsConfig,
    GeneralConfig,
    GeneratorConfig,
    LspConfig,
    PrintersConfig,
    TestingConfig,
    TopLevelConfig,
)

logger = get_logger(__name__)


class UnsupportedPlatformError(Exception):
    """
    The current platform is not supported. Supported platforms are: Linux, macOS, Windows.
    """


class WokeConfig:
    __project_root_path: Path
    __global_config_path: Path
    __global_data_path: Path
    __loaded_files: Set[Path]
    __config_raw: Dict[str, Any]
    __config: TopLevelConfig

    def __init__(
        self,
        *_,
        project_root_path: Optional[Union[str, Path]] = None,
    ):
        system = platform.system()

        try:
            self.__global_config_path = Path(os.environ["XDG_CONFIG_HOME"]) / "woke"
        except KeyError:
            if system in {"Linux", "Darwin"}:
                self.__global_config_path = Path.home() / ".config" / "woke"
            elif system == "Windows":
                self.__global_config_path = Path(os.environ["LOCALAPPDATA"]) / "woke"
            else:
                raise UnsupportedPlatformError(f"Platform `{system}` is not supported.")

        try:
            self.__global_data_path = Path(os.environ["XDG_DATA_HOME"]) / "woke"
        except KeyError:
            if system in {"Linux", "Darwin"}:
                self.__global_data_path = Path.home() / ".local" / "share" / "woke"
            elif system == "Windows":
                self.__global_data_path = Path(os.environ["LOCALAPPDATA"]) / "woke"
            else:
                raise UnsupportedPlatformError(f"Platform `{system}` is not supported.")

        migrate = False
        if (
            not self.__global_config_path.exists()
            and not self.__global_data_path.exists()
        ):
            migrate = True

        self.__global_config_path.mkdir(parents=True, exist_ok=True)
        self.__global_data_path.mkdir(parents=True, exist_ok=True)

        if migrate:
            if system == "Linux":
                old_path = Path.home() / ".config" / "Woke"
            elif system == "Darwin":
                old_path = Path.home() / ".config" / "Woke"
            elif system == "Windows":
                old_path = Path.home() / "Woke"
            else:
                raise UnsupportedPlatformError(f"Platform `{system}` is not supported.")

            config_path = old_path / "config.toml"
            compilers_path = old_path / "compilers"
            solc_versions_path = old_path / ".woke_solc_version"

            if config_path.exists():
                config_path.rename(self.__global_config_path / "config.toml")
            if compilers_path.exists():
                compilers_path.rename(self.__global_data_path / "compilers")
            if solc_versions_path.exists():
                solc_versions_path.rename(
                    self.__global_data_path / ".woke_solc_version"
                )

            try:
                old_path.rmdir()
            except OSError:
                pass

        if project_root_path is None:
            self.__project_root_path = Path.cwd().resolve()
        else:
            self.__project_root_path = Path(project_root_path).resolve()

        if not self.__project_root_path.is_dir():
            raise ValueError(
                f"Project root path '{self.__project_root_path}' is not a directory."
            )

        self.__loaded_files = set()
        with change_cwd(self.__project_root_path):
            self.__config = TopLevelConfig()
        self.__config_raw = self.__config.dict(by_alias=True)

    def __str__(self) -> str:
        return self.__config.json(by_alias=True, exclude_unset=True)

    def __repr__(self) -> str:
        config_dict = reprlib.repr(self.__config_raw)
        return f"{self.__class__.__name__}.fromdict({config_dict}, project_root_path={repr(self.__project_root_path)})"

    def __merge_dicts(self, old: Dict[str, Any], new: Dict[str, Any]) -> None:
        for k, v in new.items():
            if k not in old.keys():
                old[k] = v
            else:
                if isinstance(v, dict):
                    self.__merge_dicts(old[k], new[k])
                else:
                    old[k] = v

    def __modified_keys(self, old: Dict, new: Dict, result: Dict) -> None:
        for k, v in new.items():
            if k not in old.keys():
                result[k] = v
            else:
                if isinstance(v, dict):
                    result[k] = {}
                    self.__modified_keys(old[k], new[k], result[k])
                    if not result[k]:
                        del result[k]
                else:
                    if old[k] != v:
                        result[k] = v
        for k, v in old.items():
            if k not in new.keys():
                result[k] = None

    def __load_file(
        self,
        parent: Optional[Path],
        path: Path,
        new_config: Dict[str, Any],
        graph: nx.DiGraph,
    ) -> None:
        if not path.is_file():
            if parent is None:
                logger.info(f"Config file '{path}' does not exist.")
            else:
                logger.warning(
                    f"Config file '{path}' loaded from '{parent}' does not exist."
                )
        else:
            # change the current working dir so that we can resolve relative paths
            with change_cwd(path.parent):
                with path.open("rb") as f:
                    loaded_config = tomli.load(f)

                graph.add_node(path, config=loaded_config)
                if parent is not None:
                    graph.add_edge(parent, path)

                # detect cyclic subconfigs
                if not nx.is_directed_acyclic_graph(graph):
                    cycles = list(nx.simple_cycles(graph))
                    error = f"Found cyclic config subconfigs:"
                    for no, cycle in enumerate(cycles):
                        error += f"\nCycle {no}:\n"
                        for path in cycle:
                            error += f"{path}\n"
                    raise ValueError(error)

                # validate the loaded config
                parsed_config = TopLevelConfig.parse_obj(loaded_config)

                # rebuild the loaded config from the pydantic model
                # this ensures that all stored paths are absolute
                loaded_config = parsed_config.dict(by_alias=True, exclude_unset=True)

                # merge the original config and the newly loaded config
                self.__merge_dicts(new_config, loaded_config)

                for subconfig_path in parsed_config.subconfigs:
                    self.__load_file(path, subconfig_path, new_config, graph)

    @classmethod
    def fromdict(
        cls,
        config_dict: Dict[str, Any],
        *_,
        project_root_path: Optional[Union[str, Path]] = None,
    ) -> "WokeConfig":
        """
        Build `WokeConfig` class from a dictionary and optional Woke root and project root paths.
        """
        instance = cls(project_root_path=project_root_path)
        with change_cwd(instance.project_root_path):
            parsed_config = TopLevelConfig.parse_obj(config_dict)
        instance.__config_raw = parsed_config.dict(by_alias=True, exclude_unset=True)
        instance.__config = parsed_config
        return instance

    def update(
        self,
        config_dict: Dict[str, Any],
        deleted_options: Iterable[Tuple[Union[int, str], ...]],
    ) -> Dict:
        """
        Update the config with a new dictionary. Return `True` if the config was changed.
        """
        with change_cwd(self.project_root_path):
            parsed_config = TopLevelConfig.parse_obj(config_dict)
        parsed_config_raw = parsed_config.dict(by_alias=True, exclude_unset=True)

        original_config = deepcopy(self.__config_raw)
        self.__merge_dicts(self.__config_raw, parsed_config_raw)

        for deleted_option in deleted_options:
            conf = self.__config_raw
            skip = False
            for segment in deleted_option[:-1]:
                if segment in conf:
                    conf = conf[segment]  # type: ignore
                else:
                    skip = True
                    break

            if skip:
                continue
            if isinstance(conf, dict):
                conf.pop(deleted_option[-1], None)  # type: ignore
            elif isinstance(conf, list):
                try:
                    conf.remove(deleted_option[-1])
                except ValueError:
                    pass

        self.__config = TopLevelConfig.parse_obj(self.__config_raw)
        modified_keys = {}
        self.__modified_keys(
            original_config,
            self.__config.dict(by_alias=True, exclude_unset=True),
            modified_keys,
        )
        return modified_keys

    def load_configs(self) -> None:
        """
        Clear any previous config options and load both the global config file `config.toml`
        located in the Woke root directory and the project specific config file `woke.toml`
        located in the project root directory. This is expected to be called right after `WokeConfig`
        instantiation.
        """
        self.__loaded_files = set()
        with change_cwd(self.__project_root_path):
            self.__config = TopLevelConfig()
        self.__config_raw = self.__config.dict(by_alias=True)

        self.load(self.global_config_path / "config.toml")
        self.load(self.project_root_path / "woke.toml")

    def load(self, path: Path) -> None:
        """
        Load config from the provided file path. Any already loaded config options are overridden by the options loaded
        from this file.
        """
        subconfigs_graph = nx.DiGraph()
        config_raw_copy = deepcopy(self.__config_raw)

        self.__load_file(None, path.resolve(), config_raw_copy, subconfigs_graph)

        config = TopLevelConfig.parse_obj(config_raw_copy)
        self.__config_raw = config_raw_copy
        self.__config = config
        self.__loaded_files.update(
            subconfigs_graph.nodes  # pyright: ignore reportGeneralTypeIssues
        )

    @property
    def loaded_files(self) -> FrozenSet[Path]:
        """
        Return frozenset of all loaded config file paths, including files that were loaded using the `subconfigs` config key.
        """
        return frozenset(self.__loaded_files)

    @property
    def global_config_path(self) -> Path:
        """
        Return the system path to the global config file.
        """
        return self.__global_config_path

    @property
    def global_data_path(self) -> Path:
        """
        Return the system path to the global data directory.
        """
        return self.__global_data_path

    @property
    def project_root_path(self) -> Path:
        """
        Return the system path of the currently open project.
        """
        return self.__project_root_path

    @property
    def min_solidity_version(self) -> SolidityVersion:
        return SolidityVersion.fromstring("0.6.2")

    @property
    def max_solidity_version(self) -> SolidityVersion:
        return SolidityVersion.fromstring("0.8.21")

    @property
    def detectors(self) -> DetectorsConfig:
        return self.__config.detectors

    @property
    def api_keys(self) -> Dict[str, str]:
        return self.__config.api_keys

    @property
    def compiler(self) -> CompilerConfig:
        """
        Return compiler-specific config options.
        """
        return self.__config.compiler

    @property
    def generator(self) -> GeneratorConfig:
        """
        Return config options specific to assets generated by Woke.
        """
        return self.__config.generator

    @property
    def lsp(self) -> LspConfig:
        """
        Return LSP-specific config options.
        """
        return self.__config.lsp

    @property
    def testing(self) -> TestingConfig:
        """
        Return testing framework-specific config options.
        """
        return self.__config.testing

    @property
    def deployment(self) -> DeploymentConfig:
        """
        Return deployment-specific config options.
        """
        return self.__config.deployment

    @property
    def general(self) -> GeneralConfig:
        """
        Return general config options.
        """
        return self.__config.general

    @property
    def printers(self) -> PrintersConfig:
        """
        Return printer-specific config options.
        """
        return self.__config.printers
