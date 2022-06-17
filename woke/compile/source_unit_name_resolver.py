from pathlib import Path, PurePath, PurePosixPath
from typing import List

from woke.config import WokeConfig
from woke.config.data_model import SolcRemapping


class SourceUnitNameResolver:
    """
    The main purpose of this class is to convert an import string into a source unit name. This is done with respect
    to https://docs.soliditylang.org/en/v0.8.11/path-resolution.html.
    """

    __config: WokeConfig

    def __init__(self, woke_config: WokeConfig):
        self.__config = woke_config

    def __apply_remapping(self, parent_source_unit: str, source_unit_name: str) -> str:
        """
        Try to apply a remapping and return a source unit name. Up to one remapping can be applied to a single import.
        It is the longest one. In case of multiple remappings with the same length, the one specified last wins.
        """
        matching_remappings: List[SolcRemapping] = []
        for remapping in self.__config.compiler.solc.remappings:
            context, prefix, target = remapping  # type: ignore
            context_matches = (context is None) or (
                context is not None and parent_source_unit.startswith(context)
            )
            if context_matches and source_unit_name.startswith(prefix):
                matching_remappings.append(remapping)

        if len(matching_remappings) == 0:
            return source_unit_name

        longest = max(matching_remappings, key=lambda r: len(r.context or ""))  # type: ignore
        remapping = next(
            r
            for r in reversed(matching_remappings)
            if len(r.context or "") == len(longest.context or "")  # type: ignore
        )
        return source_unit_name.replace(remapping.prefix, remapping.target, 1)  # type: ignore

    def __resolve_direct_import(self, parent_source_unit: str, import_str: str) -> str:
        """
        Return a source unit name of a direct import in the file with given source unit name.
        """
        return self.__apply_remapping(parent_source_unit, import_str)

    def __resolve_relative_import(
        self, parent_source_unit: str, import_str: str
    ) -> str:
        """
        Return a source unit name of a relative import in the file with given source unit name.
        """
        import_parts = [i for i in import_str.split("/") if i not in {"", "."}]
        parent_parts = parent_source_unit.split("/")
        while len(parent_parts) > 0 and parent_parts[-1] == "":
            parent_parts.pop()
        if len(parent_parts) > 0:
            parent_parts.pop()
        while len(parent_parts) > 0 and parent_parts[-1] == "":
            parent_parts.pop()

        normalized_import_parts = []
        for part in import_parts:
            if part == "..":
                if (
                    len(normalized_import_parts) == 0
                    or normalized_import_parts[-1] == ".."
                ):
                    normalized_import_parts.append("..")
                else:
                    normalized_import_parts.pop()
            else:
                normalized_import_parts.append(part)

        for no, part in enumerate(normalized_import_parts):
            if part == "..":
                while len(parent_parts) > 0 and parent_parts[-1] == "":
                    parent_parts.pop()
                if len(parent_parts) > 0:
                    parent_parts.pop()
            else:
                normalized_import_parts = normalized_import_parts[no:]
                break

        if len(parent_parts) > 0:
            source_unit_name = (
                "/".join(parent_parts) + "/" + "/".join(normalized_import_parts)
            )
        else:
            source_unit_name = "/".join(normalized_import_parts)
        return self.__apply_remapping(parent_source_unit, source_unit_name)

    def resolve_import(self, parent_source_unit: str, import_str: str) -> str:
        """
        Resolve a source unit name of an import in the file with given source unit name.
        """
        if import_str.startswith(("./", "../")):
            return self.__resolve_relative_import(parent_source_unit, import_str)
        return self.__resolve_direct_import(parent_source_unit, import_str)

    def resolve_cmdline_arg(self, arg: str) -> str:
        """
        Return a source unit name of the file provided as a command-line argument.
        """
        path = Path(arg).resolve(strict=True)
        pure_path = PurePath(path)
        rel_path = pure_path.relative_to(self.__config.project_root_path)
        return str(PurePosixPath(rel_path))
