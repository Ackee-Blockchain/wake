import re
from pathlib import Path
from typing import List, Tuple

from Cryptodome.Hash import BLAKE2b

from woke.core.solidity_version import (
    SolidityVersionExpr,
    SolidityVersionRange,
    SolidityVersionRanges,
)

from .solidity_import import SolidityImportExpr

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
    MULTILINE_COMMENT_END_RE = re.compile(r"\*/")
    ONELINE_COMMENT_OR_MULTILINE_COMMENT_START_RE = re.compile(
        r"(//.*$|/\*)", re.MULTILINE
    )

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
    def __parse_version_pragma(
        cls, source_code: str, ignore_errors: bool
    ) -> SolidityVersionRanges:
        versions = None
        matches = cls.PRAGMA_SOLIDITY_RE.finditer(source_code)
        for match in matches:
            s = source_code[0 : match.start()].splitlines()
            if len(s) > 0:
                # ignore pragmas in a string
                if not cls.__string_closed(s[-1]):
                    continue

            version_str = match.groupdict()["version"]
            try:
                version_expr = SolidityVersionExpr(version_str)
            except ValueError:
                if ignore_errors:
                    continue
                raise
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
    def __parse_import(cls, source_code: str, ignore_errors: bool) -> List[str]:
        imports = set()  # avoid listing the same import multiple times
        matches = cls.IMPORT_RE.finditer(source_code)
        for match in matches:
            s = source_code[0 : match.start()].splitlines()
            if len(s) > 0:
                # ignore imports in a string
                if not cls.__string_closed(s[-1]):
                    continue

            import_str = match.groupdict()["import"]
            try:
                import_expr = SolidityImportExpr(import_str)
            except ValueError:
                if ignore_errors:
                    continue
                raise
            imports.add(import_expr.filename)
        return list(imports)

    @classmethod
    def strip_comments(cls, source_code: str) -> str:
        stop = False
        while not stop:
            # try to find a single-line or multi-line comment (whichever comes first)
            matches = cls.ONELINE_COMMENT_OR_MULTILINE_COMMENT_START_RE.finditer(
                source_code
            )
            stop = True

            for match in matches:
                s = source_code[0 : match.start()].splitlines()
                if len(s) > 0:
                    # ignore `//` and `/*` in Solidity strings
                    if not cls.__string_closed(s[-1]):
                        continue

                stop = False

                if source_code[match.start() : match.end()] == "/*":
                    # found a multi-line comment start
                    end_match = cls.MULTILINE_COMMENT_END_RE.search(
                        source_code, match.end()
                    )
                    if end_match is None:
                        raise ValueError(f"Multi-line comment not closed.")
                    source_code = (
                        source_code[0 : match.start()] + source_code[end_match.end() :]
                    )
                else:
                    # found a single-line comment
                    source_code = (
                        source_code[0 : match.start()] + source_code[match.end() :]
                    )

                break
        return source_code

    @classmethod
    def parse(
        cls, path: Path, ignore_errors: bool = False
    ) -> Tuple[SolidityVersionRanges, List[str], bytes]:
        """
        Return a tuple of two lists. The first list contains Solidity version ranges that can be used to compile
        the given file. The second list contains filenames / URLs that are imported from the given file.
        """
        raw_content = path.read_bytes()
        content = raw_content.decode("utf-8")

        h = BLAKE2b.new(data=raw_content, digest_bits=256)

        # strip all comments
        content = cls.strip_comments(content)

        return (
            cls.__parse_version_pragma(content, ignore_errors),
            cls.__parse_import(content, ignore_errors),
            h.digest(),
        )

    @classmethod
    def parse_source(
        cls,
        source_code: str,
        ignore_errors: bool = False,
    ) -> Tuple[SolidityVersionRanges, List[str], bytes]:
        """
        Return a tuple of two lists. The first list contains Solidity version ranges that can be used to compile
        the given file. The second list contains filenames / URLs that are imported from the given file.
        """
        h = BLAKE2b.new(data=source_code.encode("utf-8"), digest_bits=256)

        # strip all comments
        content = cls.strip_comments(source_code)

        return (
            cls.__parse_version_pragma(content, ignore_errors),
            cls.__parse_import(content, ignore_errors),
            h.digest(),
        )
