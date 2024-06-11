import itertools
from pathlib import Path, PurePath, PurePosixPath
from typing import List

from wake.config import WakeConfig
from wake.config.data_model import SolcRemapping
from wake.utils import wake_contracts_path


class SourceUnitNameResolver:
    """
    The main purpose of this class is to convert an import string into a source unit name. This is done with respect
    to https://docs.soliditylang.org/en/v0.8.11/path-resolution.html.
    """

    __config: WakeConfig

    def __init__(self, wake_config: WakeConfig):
        self.__config = wake_config

    def apply_remapping(self, parent_source_unit: str, source_unit_name: str) -> str:
        """
        Try to apply a remapping and return a source unit name. Up to one remapping can be applied to a single import.
        It is the longest one. In case of multiple remappings with the same length, the one specified last wins.
        """
        matching_remappings: List[SolcRemapping] = []
        for remapping in self.__config.compiler.solc.remappings:
            context, prefix, target = remapping
            context_matches = (context is None) or (
                context is not None and parent_source_unit.startswith(context)
            )
            if context_matches and source_unit_name.startswith(prefix):
                matching_remappings.append(remapping)

        if len(matching_remappings) == 0:
            return source_unit_name

        # longest prefix wins, if there are multiple remappings with the same prefix, choose the last one
        matching_remappings.sort(key=lambda r: len(r.prefix), reverse=True)

        # choose the remapping with the longest context
        # if there are multiple remappings with the same context, choose the last one
        l = len(matching_remappings[0].prefix)
        target_remapping = matching_remappings[-1]
        for i in range(1, len(matching_remappings)):
            if len(matching_remappings[i].prefix) != l:
                target_remapping = matching_remappings[i - 1]
                break

        return source_unit_name.replace(
            str(target_remapping.prefix), target_remapping.target or "", 1
        )

    def __resolve_direct_import(self, parent_source_unit: str, import_str: str) -> str:
        """
        Return a source unit name of a direct import in the file with given source unit name.
        """
        return self.apply_remapping(parent_source_unit, import_str)

    def __resolve_relative_import(
        self, parent_source_unit: str, import_str: str
    ) -> str:
        """
        Return a source unit name of a relative import in the file with given source unit name.
        """
        import_parts = [part for part in import_str.split("/") if part not in {"", "."}]
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
        return self.apply_remapping(parent_source_unit, source_unit_name)

    def resolve_import(self, parent_source_unit: str, import_str: str) -> str:
        """
        Resolve a source unit name of an import in the file with given source unit name.
        """
        if import_str.startswith((".", "..")):
            return self.__resolve_relative_import(parent_source_unit, import_str)
        return self.__resolve_direct_import(parent_source_unit, import_str)

    def resolve_cmdline_arg(self, arg: str) -> str:
        """
        Return a source unit name of the file provided as a command-line argument.
        """
        path = Path(arg).resolve()
        pure_path = PurePath(path)
        for include_path in itertools.chain(
            [self.__config.project_root_path],
            self.__config.compiler.solc.include_paths,
            [wake_contracts_path],
        ):
            try:
                return str(PurePosixPath(pure_path.relative_to(include_path)))
            except ValueError:
                pass

        raise ValueError(f"File {arg} is not in the project root dir or include paths.")
