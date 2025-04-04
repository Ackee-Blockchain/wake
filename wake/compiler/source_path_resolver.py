import itertools
from pathlib import Path
from typing import AbstractSet

from wake.config import WakeConfig

from .exceptions import CompilationResolveError


class SourcePathResolver:
    __config: WakeConfig

    def __init__(self, wake_config: WakeConfig):
        self.__config = wake_config

    def resolve(
        self,
        source_unit_name: str,
        parent_source_unit_name: str,
        virtual_files: AbstractSet[Path],
    ) -> Path:
        """
        Return a system path for the given source unit name. Currently, this is done in a single step:
        - Try to find a source file in the Wake project directory or directories provided in the `include_paths` config option.
        There may be more steps implemented in the future. For example, we can add support for GitHub URLs.
        NPM packages can be easily resolved using the `include_paths` config option.
        """
        matching_paths = set()

        for include_path in itertools.chain(
            [self.__config.project_root_path],
            self.__config.compiler.solc.include_paths,
            [self.__config.wake_contracts_path],
        ):
            path = Path(include_path / source_unit_name)
            if path.is_file():
                matching_paths.add(path)
            elif path in virtual_files:
                matching_paths.add(path)

        if len(matching_paths) == 0:
            raise CompilationResolveError(
                f"Unable to find '{source_unit_name}' imported from '{parent_source_unit_name}' in the project root dir or include paths."
            )

        if len(matching_paths) > 1:
            err = f"Source unit name '{source_unit_name}' imported from '{parent_source_unit_name}' is ambiguous. It can be included as:"
            for matching_path in matching_paths:
                err += f"\n{matching_path}"
            raise CompilationResolveError(err)
        return matching_paths.pop()

    def matches(self, source_unit_name: str, file: Path) -> bool:
        """
        Return True if the given source unit name matches the given file path.
        """
        for include_path in itertools.chain(
            [self.__config.project_root_path],
            self.__config.compiler.solc.include_paths,
            [self.__config.wake_contracts_path],
        ):
            path = include_path / source_unit_name
            if path == file:
                return True
        return False
