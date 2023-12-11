import logging
import os
import platform
import reprlib
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, FrozenSet, Iterable, Optional, Set, Tuple, Union

import networkx as nx
import tomli

from wake.core import get_logger
from wake.utils import change_cwd

from ..core.solidity_version import SolidityVersion
from .data_model import (
    CompilerConfig,
    DeploymentConfig,
    DetectorConfig,
    DetectorsConfig,
    GeneralConfig,
    GeneratorConfig,
    LspConfig,
    PrinterConfig,
    PrintersConfig,
    TestingConfig,
    TopLevelConfig,
)

logger = get_logger(__name__)


class UnsupportedPlatformError(Exception):
    """
    The current platform is not supported. Supported platforms are: Linux, macOS, Windows.
    """


class WakeConfig:
    """
    Wake configuration class. This class is responsible for loading, storing and merging all Wake config options.
    """

    __local_config_path: Path
    __project_root_path: Path
    __global_config_path: Path
    __global_data_path: Path
    __global_cache_path: Path
    __loaded_files: Set[Path]
    __config_raw: Dict[str, Any]
    __config: TopLevelConfig

    def __init__(
        self,
        *_,
        local_config_path: Optional[Union[str, Path]] = None,
        project_root_path: Optional[Union[str, Path]] = None,
    ):
        """
        Initialize the `WakeConfig` class. If `project_root_path` is not provided, the current working directory is used.
        If `local_config_path` is not provided, the `wake.toml` file in the project root directory is used.
        """
        system = platform.system()

        try:
            self.__global_config_path = (
                Path(os.environ["XDG_CONFIG_HOME"]) / "wake" / "config.toml"
            )
        except KeyError:
            if system in {"Linux", "Darwin"}:
                self.__global_config_path = (
                    Path.home() / ".config" / "wake" / "config.toml"
                )
            elif system == "Windows":
                self.__global_config_path = (
                    Path(os.environ["LOCALAPPDATA"]) / "wake" / "config.toml"
                )
            else:
                raise UnsupportedPlatformError(f"Platform `{system}` is not supported.")

        try:
            self.__global_data_path = Path(os.environ["XDG_DATA_HOME"]) / "wake"
        except KeyError:
            if system in {"Linux", "Darwin"}:
                self.__global_data_path = Path.home() / ".local" / "share" / "wake"
            elif system == "Windows":
                self.__global_data_path = Path(os.environ["LOCALAPPDATA"]) / "wake"
            else:
                raise UnsupportedPlatformError(f"Platform `{system}` is not supported.")

        try:
            self.__global_cache_path = Path(os.environ["XDG_CACHE_HOME"]) / "wake"
        except KeyError:
            if system in {"Linux", "Darwin"}:
                self.__global_cache_path = Path.home() / ".cache" / "wake"
            elif system == "Windows":
                self.__global_cache_path = Path(os.environ["TEMP"]) / "wake"
            else:
                raise UnsupportedPlatformError(f"Platform `{system}` is not supported.")

        self.__global_config_path.parent.mkdir(parents=True, exist_ok=True)
        self.__global_data_path.mkdir(parents=True, exist_ok=True)

        if project_root_path is None:
            self.__project_root_path = Path.cwd().resolve()
        else:
            self.__project_root_path = Path(project_root_path).resolve()

        if local_config_path is None:
            self.__local_config_path = self.__project_root_path / "wake.toml"
        else:
            self.__local_config_path = Path(local_config_path).resolve()

        if not self.__project_root_path.is_dir():
            raise ValueError(
                f"Project root path '{self.__project_root_path}' is not a directory."
            )

        self.__loaded_files = set()
        with change_cwd(self.__project_root_path):
            self.__config = TopLevelConfig()
        self.__config_raw = self.__config.dict(by_alias=True)

    def __str__(self) -> str:
        """
        Returns:
            JSON representation of the config.
        """
        return self.__config.json(by_alias=True, exclude_unset=True)

    def __repr__(self) -> str:
        """
        Returns:
            String representation of the config.
        """
        config_dict = reprlib.repr(self.__config_raw)
        return f"{self.__class__.__name__}.fromdict({config_dict}, config_path={repr(self.__local_config_path)}, project_root_path={repr(self.__project_root_path)})"

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
        *,
        project_root_path: Optional[Union[str, Path]] = None,
    ) -> "WakeConfig":
        """
        Args:
            config_dict: Dictionary containing the config options.
            project_root_path: Path to the project root directory.

        Returns:
            Instance of the `WakeConfig` class with the provided config options.
        """
        instance = cls(project_root_path=project_root_path)
        with change_cwd(instance.project_root_path):
            parsed_config = TopLevelConfig.parse_obj(config_dict)
        instance.__config_raw = parsed_config.dict(by_alias=True, exclude_unset=True)
        instance.__config = parsed_config
        return instance

    def todict(self) -> Dict[str, Any]:
        """
        Returns:
            Dictionary containing the config options.
        """
        return self.__config_raw

    def update(
        self,
        config_dict: Dict[str, Any],
        deleted_options: Iterable[Tuple[Union[int, str], ...]],
    ) -> Dict:
        """
        Update the config with a new dictionary.

        Args:
            config_dict: Dictionary containing the new config options.
            deleted_options: Iterable of config option paths (in the form of tuples of string keys and integer indices) that should be deleted from the config (reset to their default values).

        Returns:
            Dictionary containing the modified config options.
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
        located in the Wake root directory and the project specific local config file.
        Typically, this is expected to be called right after `WakeConfig` instantiation.
        """
        self.__loaded_files = set()
        with change_cwd(self.__project_root_path):
            self.__config = TopLevelConfig()
        self.__config_raw = self.__config.dict(by_alias=True)

        self.load(self.global_config_path)
        self.load(self.local_config_path)

    def load(self, path: Path) -> None:
        """
        Load config from the provided file path. Any already loaded config options are overridden by the options loaded
        from this file.

        Args:
            path: System path to the config file.
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
        Returns:
            All loaded config files, including files that were loaded using the `subconfigs` config key.
        """
        return frozenset(self.__loaded_files)

    @property
    def local_config_path(self) -> Path:
        """
        Returns:
            System path to the local config file.
        """
        return self.__local_config_path

    @local_config_path.setter
    def local_config_path(self, path: Path) -> None:
        """
        Args:
            path: New system path to the local config file.
        """
        self.__local_config_path = path

    @property
    def global_config_path(self) -> Path:
        """
        Returns:
            System path to the global config file.
        """
        return self.__global_config_path

    @property
    def global_data_path(self) -> Path:
        """
        Returns:
            System path to the global data directory.
        """
        return self.__global_data_path

    @property
    def global_cache_path(self) -> Path:
        """
        Returns:
            System path to the global cache directory.
        """
        return self.__global_cache_path

    @property
    def project_root_path(self) -> Path:
        """
        Returns:
            System path to the project root directory.
        """
        return self.__project_root_path

    @property
    def min_solidity_version(self) -> SolidityVersion:
        """
        Returns:
            Minimum supported Solidity version.
        """
        return SolidityVersion.fromstring("0.6.2")

    @property
    def max_solidity_version(self) -> SolidityVersion:
        """
        Returns:
            Maximum supported Solidity version.
        """
        return SolidityVersion.fromstring("0.8.23")

    @property
    def detectors(self) -> DetectorsConfig:
        """
        Returns:
            General config options for all detectors.
        """
        return self.__config.detectors

    @property
    def detector(self) -> DetectorConfig:
        """
        Returns:
            Per-detector config options.
        """
        return self.__config.detector

    @property
    def api_keys(self) -> Dict[str, str]:
        """
        Returns:
            API keys for various services.
        """
        return self.__config.api_keys

    @property
    def compiler(self) -> CompilerConfig:
        """
        Returns:
            Compiler config options.
        """
        return self.__config.compiler

    @property
    def generator(self) -> GeneratorConfig:
        """
        Returns:
            Config options for specific to assets generated by Wake.
        """
        return self.__config.generator

    @property
    def lsp(self) -> LspConfig:
        """
        Returns:
            LSP config options.
        """
        return self.__config.lsp

    @property
    def testing(self) -> TestingConfig:
        """
        Returns:
            Testing config options.
        """
        return self.__config.testing

    @property
    def deployment(self) -> DeploymentConfig:
        """
        Returns:
            Deployment config options.
        """
        return self.__config.deployment

    @property
    def general(self) -> GeneralConfig:
        """
        Returns:
            General config options.
        """
        return self.__config.general

    @property
    def printers(self) -> PrintersConfig:
        """
        Returns:
            General config options for all printers.
        """
        return self.__config.printers

    @property
    def printer(self) -> PrinterConfig:
        """
        Returns:
            Per-printer config options.
        """
        return self.__config.printer
