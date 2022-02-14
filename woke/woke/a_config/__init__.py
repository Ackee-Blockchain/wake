import reprlib
from typing import Optional, Union, Dict, Any, List, Set, FrozenSet
from pathlib import Path
from copy import deepcopy
import platform
import logging
import pprint
import os
import re

from pydantic import BaseModel, Extra, Field, validator
from pydantic.dataclasses import dataclass
import networkx as nx
import tomli

"""
This module handles config file management. Each config option has its default value.
There are two main sources of config files:
* `config.toml` global config file in the Woke root directory ($HOME/.woke on macOS and Linux, $HOME/Woke on Windows)
* `woke-config.toml` project-specific config file present in a project root directory

There may be additional config files included with the `imports` top-level config key. Paths in the `imports` key can
be both relative and absolute.

Config options can be overridden. Imported config options override the options in the original file. Order of files
listed in `imports` also matters. Latter files in the list override earlier files. Config options loaded from the
global `config.toml` file can be overridden by options supplied through project-specific config files.

While this module enforces valid syntax of config files, it does not (and cannot) verify the semantics of the provided
config values. Extra config keys that are not specified in the documentation are forbidden.
"""


class UnsupportedPlatformError(Exception):
    """
    The current platform is not supported. Supported platforms are: Linux, macOS, Windows.
    """


class WokeConfigModel(BaseModel):
    class Config:
        allow_mutation = False
        extra = Extra.forbid


@dataclass
class SolcRemapping:
    context: Optional[str]
    prefix: str
    target: Optional[str]


class SolcWokeConfig(WokeConfigModel):
    remappings: List[SolcRemapping] = []

    @validator("remappings", pre=True, each_item=True)
    def set_remapping(cls, v):
        remapping_re = re.compile(
            r"(?:(?P<context>[^:\s]+)?:)?(?P<prefix>[^\s=]+)=(?P<target>[^\s]+)?"
        )
        match = remapping_re.match(v)
        assert match, f"`{v}` is not a valid solc remapping."

        groupdict = match.groupdict()
        context = groupdict["context"]
        prefix = groupdict["prefix"]
        target = groupdict["target"]
        return SolcRemapping(context, prefix, target)


class TopLevelWokeConfig(WokeConfigModel):
    imports: List[str] = []
    solc: SolcWokeConfig = Field(default_factory=SolcWokeConfig)


class WokeConfig:
    __woke_root_path: Path
    __project_root_path: Path
    __loaded_files: Set[Path]
    __config_raw: Dict[str, Any]
    __config: TopLevelWokeConfig

    def __init__(
        self,
        *_,
        project_root_path: Optional[Union[str, Path]] = None,
        woke_root_path: Optional[Union[str, Path]] = None,
    ):
        if woke_root_path is None:
            system = platform.system()
            if system == "Linux":
                self.__woke_root_path = Path.home() / ".woke"
            elif system == "Darwin":
                self.__woke_root_path = Path.home() / ".woke"
            elif system == "Windows":
                self.__woke_root_path = Path.home() / "Woke"
            else:
                raise UnsupportedPlatformError(f"Platform `{system}` is not supported.")
        else:
            self.__woke_root_path = Path(woke_root_path)

        if project_root_path is None:
            self.__project_root_path = Path.cwd().resolve()
        else:
            self.__project_root_path = Path(project_root_path).resolve()

        if not self.__project_root_path.is_dir():
            raise ValueError(
                f"Project root path `{self.__project_root_path}` is not a directory."
            )

        # make sure that Woke root path exists
        self.__woke_root_path.mkdir(parents=True, exist_ok=True)
        self.__woke_root_path = self.__woke_root_path.resolve(strict=True)

        self.__loaded_files = set()
        self.__config_raw = dict()
        self.__config = TopLevelWokeConfig()

    def __str__(self) -> str:
        return pprint.pformat(self.__config_raw, indent=4)

    def __repr__(self) -> str:
        config_dict = reprlib.repr(self.__config_raw)
        return f"{self.__class__.__name__}.fromdict({config_dict}, project_root_path={repr(self.__project_root_path)}, woke_root_path={repr(self.__woke_root_path)})"

    def __load_file(
        self,
        parent: Optional[Path],
        path: Path,
        new_config: Dict[str, Any],
        graph: nx.DiGraph,
    ) -> None:
        if not path.is_file():
            if parent is None:
                logging.warning(f"Config file `{path}` does not exist.")
            else:
                logging.warning(
                    f"Config file `{path}` imported from `{parent}` does not exist."
                )
        else:
            with path.open("rb") as f:
                loaded_config = tomli.load(f)

            graph.add_node(path, config=loaded_config)
            if parent is not None:
                graph.add_edge(parent, path)

            # detect cyclic imports
            if not nx.is_directed_acyclic_graph(graph):
                cycles = list(nx.simple_cycles(graph))
                error = f"Found cyclic config imports:"
                for no, cycle in enumerate(cycles):
                    error += f"\nCycle {no}:\n"
                    for path in cycle:
                        error += f"{path}\n"
                raise ValueError(error)

            # validate loaded config
            parsed_config = TopLevelWokeConfig.parse_obj(loaded_config)

            # merge the original config and the newly loaded config
            new_config.update(loaded_config)

            for import_file in parsed_config.imports:
                if os.path.isabs(import_file):
                    import_path = Path(import_file).resolve()
                else:
                    import_path = (path.parent / import_file).resolve()
                self.__load_file(path, import_path, new_config, graph)

    @classmethod
    def fromdict(
        cls,
        config_dict: Dict[str, Any],
        *_,
        project_root_path: Optional[Union[str, Path]] = None,
        woke_root_path: Optional[Union[str, Path]] = None,
    ) -> "WokeConfig":
        """
        Build `WokeConfig` class from a dictionary and an optional Woke root path.
        """
        instance = cls(
            project_root_path=project_root_path, woke_root_path=woke_root_path
        )
        config = TopLevelWokeConfig.parse_obj(config_dict)
        instance.__config_raw = deepcopy(config_dict)
        instance.__config = config
        return instance

    def load_configs(self) -> None:
        """
        Load both the global config file `config.toml` located in the Woke root directory
        and the project specific config file `woke-config.toml` located in the project root directory.
        This is expected to be called right after `WokeConfig` instantiation.
        """
        self.load(self.woke_root_path / "config.toml")
        self.load(self.project_root_path / "woke-config.toml")

    def load(self, path: Path) -> None:
        """
        Load config from the provided file path. Any already loaded config options are overridden by the options loaded
        from this file.
        """
        imports_graph = nx.DiGraph()
        config_raw_copy = deepcopy(self.__config_raw)

        self.__load_file(None, path.resolve(), config_raw_copy, imports_graph)

        # validate newly loaded config
        config = TopLevelWokeConfig.parse_obj(config_raw_copy)
        self.__config_raw = config_raw_copy
        self.__config = config
        self.__loaded_files.update(imports_graph.nodes)

    @property
    def loaded_files(self) -> FrozenSet[Path]:
        """
        Return frozenset of all loaded config file paths, including files that were loaded using the `imports` config key.
        """
        return frozenset(self.__loaded_files)

    @property
    def woke_root_path(self) -> Path:
        """
        Return the system path to the Woke root directory.
        """
        return self.__woke_root_path

    @property
    def project_root_path(self) -> Path:
        """
        Return the system path of the currently open project.
        """
        return self.__project_root_path

    @property
    def solc(self) -> SolcWokeConfig:
        """
        Return `solc` specific config options.
        """
        return self.__config.solc
