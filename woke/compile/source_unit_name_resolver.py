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

    def __apply_remapping(
        self, parent_source_unit: PurePath, source_unit_name: PurePath
    ) -> PurePath:
        """
        Try to apply a remapping and return a source unit name. Up to one remapping can be applied to a single import.
        It is the longest one. In case of multiple remappings with the same length, the one specified last wins.
        """
        matching_remappings: List[SolcRemapping] = []
        for remapping in self.__config.compiler.solc.remappings:
            context, prefix, target = remapping
            context_matches = (context is None) or (
                context is not None
                and str(parent_source_unit).startswith(str(PurePath(context)))
            )
            if context_matches and str(source_unit_name).startswith(
                str(PurePath(prefix))
            ):
                matching_remappings.append(remapping)

        if len(matching_remappings) == 0:
            return source_unit_name

        longest = max(matching_remappings, key=lambda r: len(r.context or ""))  # type: ignore
        remapping = next(
            r
            for r in reversed(matching_remappings)
            if len(r.context or "") == len(longest.context or "")  # type: ignore
        )
        return PurePath(
            str(source_unit_name).replace(
                str(PurePath(remapping.prefix)), remapping.target or "", 1
            )
        )

    def __resolve_direct_import(
        self, parent_source_unit: PurePath, import_path: PurePath
    ) -> PurePath:
        """
        Return a source unit name of a direct import in the file with given source unit name.
        """
        return self.__apply_remapping(parent_source_unit, import_path)

    def __resolve_relative_import(
        self, parent_source_unit: PurePath, import_path: PurePath
    ) -> PurePath:
        """
        Return a source unit name of a relative import in the file with given source unit name.
        """
        import_parts = [
            part for part in import_path.parts if str(part) not in {"", "."}
        ]
        parent_parts = list(parent_source_unit.parts)

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
            source_unit_name = PurePath(parent_parts[0])
            for part in parent_parts[1:]:
                source_unit_name = source_unit_name / part
            for part in normalized_import_parts:
                source_unit_name = source_unit_name / part
        else:
            source_unit_name = PurePath(normalized_import_parts[0])
            for part in normalized_import_parts[1:]:
                source_unit_name = source_unit_name / part
        return self.__apply_remapping(parent_source_unit, source_unit_name)

    def resolve_import(self, parent_source_unit: PurePath, import_str: str) -> PurePath:
        """
        Resolve a source unit name of an import in the file with given source unit name.
        """
        try:
            import_path = PurePath(import_str.encode("utf-8").decode("unicode-escape"))
        except UnicodeDecodeError:
            import_path = PurePath(import_str)
        if import_str.startswith((".", "..")):
            return self.__resolve_relative_import(parent_source_unit, import_path)
        return self.__resolve_direct_import(parent_source_unit, import_path)

    def resolve_cmdline_arg(self, arg: str) -> PurePath:
        """
        Return a source unit name of the file provided as a command-line argument.
        """
        path = Path(arg).resolve(strict=True)
        pure_path = PurePath(path)
        return pure_path.relative_to(self.__config.project_root_path)
