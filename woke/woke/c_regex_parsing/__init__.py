from typing import Tuple, List
from pathlib import Path
import re

from woke.c_regex_parsing.a_version import (
    SolidityVersionExpr,
    SolidityVersionRange,
    SolidityVersionRanges,
    SolidityVersion,
)
from woke.c_regex_parsing.b_import import SolidityImportExpr

# TODO Raise error on `pragma` or `import` in contract definition
# Instead of parsing `pragma solidity` and `import` statements inside a contract definition, we should raise an exception.
# example:
# ```
# contract b {
#     pragma solidity ^0.8.0;
# }
# ```
# assignees: michprev


class SoliditySourceParser:
    PRAGMA_SOLIDITY_RE = re.compile(r"pragma\s+solidity\s+(?P<version>[^;]+)\s*;")
    IMPORT_RE = re.compile(r"import\s*(?P<import>[^;]+)\s*;")
    ONELINE_COMMENT_RE = re.compile(r"//.*$", re.MULTILINE)
    MULTILINE_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)

    @classmethod
    def __string_closed(cls, line: str) -> bool:
        opening_char = None
        for i in range(len(line)):
            if opening_char is None:
                if line[i] in {'"', "'"}:
                    opening_char = line[i]
            else:
                if line[i] == opening_char:
                    if i > 0 and line[i - 1] == "\\":
                        continue
                    else:
                        opening_char = None
        return opening_char is None

    @classmethod
    def __parse_version_pragma(cls, source_code: str) -> SolidityVersionRanges:
        versions = None
        matches = cls.PRAGMA_SOLIDITY_RE.finditer(source_code)
        for match in matches:
            s = source_code[0 : match.start()].splitlines()
            if len(s) > 0:
                # ignore pragmas in a string
                if not cls.__string_closed(s[-1]):
                    continue

            version_str = match.groupdict()["version"]
            version_expr = SolidityVersionExpr(version_str)
            if versions is None:
                versions = version_expr.version_ranges
            else:
                # in case of multiple version pragmas in a single file, intersection is performed
                versions &= version_expr.version_ranges

        # any version can be used when no pragma solidity present
        if versions is None:
            versions = SolidityVersionRanges(
                [SolidityVersionRange("0.0.0", True, None, None)]
            )
        return versions

    @classmethod
    def __parse_import(cls, source_code: str) -> List[str]:
        imports = set()  # avoid listing the same import multiple times
        matches = cls.IMPORT_RE.finditer(source_code)
        for match in matches:
            s = source_code[0 : match.start()].splitlines()
            if len(s) > 0:
                # ignore imports in a string
                if not cls.__string_closed(s[-1]):
                    continue

            import_str = match.groupdict()["import"]
            import_expr = SolidityImportExpr(import_str)
            imports.add(import_expr.filename)
        return list(imports)

    @classmethod
    def parse(cls, path: Path) -> Tuple[SolidityVersionRanges, List[str]]:
        """
        Return a tuple of two lists. The first list contains Solidity version ranges that can be used to compile
        the given file. The second list contains filenames / URLs that are imported from the given file.
        """
        content = path.read_text(encoding="utf-8")

        # strip all comments
        content = cls.ONELINE_COMMENT_RE.sub("", content)
        content = cls.MULTILINE_COMMENT_RE.sub("", content)

        return cls.__parse_version_pragma(content), cls.__parse_import(content)
