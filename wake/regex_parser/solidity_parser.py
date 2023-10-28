import re
from collections import defaultdict
from pathlib import Path
from typing import DefaultDict, Dict, List, Optional, Tuple, Union

from Crypto.Hash import BLAKE2b

from wake.core.solidity_version import (
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
    PRAGMA_SOLIDITY_RE = re.compile(rb"pragma\s+solidity\s+(?P<version>[^;]+)\s*;")
    IMPORT_RE = re.compile(rb"""import\s*(?P<import>[\s"*{][^;]+)\s*;""")
    MULTILINE_COMMENT_END_RE = re.compile(rb"\*/")
    ONELINE_COMMENT_OR_MULTILINE_COMMENT_START_RE = re.compile(
        rb"(//.*$|/\*)", re.MULTILINE
    )

    WAKE_DISABLE_NEXT_LINE_RE = re.compile(
        rb"^\s*wake-disable-next-line\s*([a-zA-Z0-9_-]*(?:\s*,\s*[a-zA-Z0-9_-]+)*)"
    )
    WAKE_DISABLE_LINE_RE = re.compile(
        rb"^\s*wake-disable-line\s*([a-zA-Z0-9_-]*(?:\s*,\s*[a-zA-Z0-9_-]+)*)"
    )
    WAKE_DISABLE_RE = re.compile(
        rb"^\s*wake-disable(?:\s|$)\s*([a-zA-Z0-9_-]*(?:\s*,\s*[a-zA-Z0-9_-]+)*)"
    )
    WAKE_ENABLE_RE = re.compile(
        rb"^\s*wake-enable\s*([a-zA-Z0-9_-]*(?:\s*,\s*[a-zA-Z0-9_-]+)*)"
    )

    @staticmethod
    def _string_closed(line: Union[str, bytes]) -> bool:
        opening_char = None
        for i in range(len(line)):
            if opening_char is None:
                if line[i] in {'"', "'", ord('"'), ord("'")}:
                    opening_char = line[i]
            else:
                if line[i] == opening_char:
                    if i > 0 and line[i - 1] in {"\\", b"\\"[0]}:
                        continue
                    else:
                        opening_char = None
        return opening_char is None

    @classmethod
    def _parse_wake_comment(cls, comment: bytes) -> Optional[Tuple[str, List[str]]]:
        comment = comment[2:]  # remove leading // or /*
        wake_disable_next_line = cls.WAKE_DISABLE_NEXT_LINE_RE.search(comment)
        if wake_disable_next_line:
            d = [
                d.decode("utf-8").strip()
                for d in wake_disable_next_line.groups()[0].split(b",")
                if len(d) > 0
            ]
            return "wake-disable-next-line", d
        wake_disable_line = cls.WAKE_DISABLE_LINE_RE.search(comment)
        if wake_disable_line:
            d = [
                d.decode("utf-8").strip()
                for d in wake_disable_line.groups()[0].split(b",")
                if len(d) > 0
            ]
            return "wake-disable-line", d
        wake_disable = cls.WAKE_DISABLE_RE.search(comment)
        if wake_disable:
            d = [
                d.decode("utf-8").strip()
                for d in wake_disable.groups()[0].split(b",")
                if len(d) > 0
            ]
            return "wake-disable", d
        wake_enable = cls.WAKE_ENABLE_RE.search(comment)
        if wake_enable:
            d = [
                d.decode("utf-8").strip()
                for d in wake_enable.groups()[0].split(b",")
                if len(d) > 0
            ]
            return "wake-enable", d
        return None

    @classmethod
    def _parse_version_pragma(
        cls, source_code: bytes, ignore_errors: bool
    ) -> SolidityVersionRanges:
        versions = None
        matches = cls.PRAGMA_SOLIDITY_RE.finditer(source_code)
        for match in matches:
            last_line_index = source_code.rfind(b"\n", 0, match.start())
            if last_line_index == -1:
                last_line_index = 0
            else:
                last_line_index += 1

            if last_line_index < match.start():
                # ignore `//` and `/*` in Solidity strings
                if not cls._string_closed(source_code[last_line_index : match.start()]):
                    continue

            version_str = match.groupdict()["version"]
            try:
                version_expr = SolidityVersionExpr(version_str.decode("utf-8"))
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
    def _parse_import(cls, source_code: bytes, ignore_errors: bool) -> List[str]:
        imports = set()  # avoid listing the same import multiple times
        matches = cls.IMPORT_RE.finditer(source_code)
        for match in matches:
            last_line_index = source_code.rfind(b"\n", 0, match.start())
            if last_line_index == -1:
                last_line_index = 0
            else:
                last_line_index += 1

            if last_line_index < match.start():
                # ignore `//` and `/*` in Solidity strings
                if not cls._string_closed(source_code[last_line_index : match.start()]):
                    continue

            import_str = match.groupdict()["import"]
            try:
                import_expr = SolidityImportExpr(import_str.decode("utf-8"))
            except ValueError:
                if ignore_errors:
                    continue
                raise
            imports.add(import_expr.filename)
        return list(imports)

    @classmethod
    def strip_comments(
        cls, source_code: bytearray
    ) -> Dict[str, List[Tuple[List[str], Tuple[int, int]]]]:
        if len(source_code) == 0:
            return {}

        wake_comments: DefaultDict[
            str, List[Tuple[List[str], Tuple[int, int]]]
        ] = defaultdict(list)
        stripped_sum = 0
        search_start = 0

        while len(source_code) > search_start:
            match = cls.ONELINE_COMMENT_OR_MULTILINE_COMMENT_START_RE.search(
                source_code, search_start
            )
            if match is None:
                break

            last_line_index = source_code.rfind(b"\n", 0, match.start())
            if last_line_index == -1:
                last_line_index = 0
            else:
                last_line_index += 1

            if last_line_index < match.start():
                # ignore `//` and `/*` in Solidity strings
                if not cls._string_closed(source_code[last_line_index : match.start()]):
                    search_start = match.end()
                    continue

            if source_code[match.start() : match.end()] == b"/*":
                end_match = cls.MULTILINE_COMMENT_END_RE.search(
                    source_code, match.end()
                )
                if end_match is None:
                    source_code[match.start() :] = b""
                    break
                wake_comment = cls._parse_wake_comment(
                    source_code[match.start() : end_match.end()]
                )
                if wake_comment is not None:
                    wake_comments[wake_comment[0]].append(
                        (
                            wake_comment[1],
                            (
                                match.start() + stripped_sum,
                                end_match.end() + stripped_sum,
                            ),
                        )
                    )

                source_code[match.start() : end_match.end()] = b""
                stripped = end_match.end() - match.start()
            else:
                wake_comment = cls._parse_wake_comment(
                    source_code[match.start() : match.end()]
                )
                if wake_comment is not None:
                    wake_comments[wake_comment[0]].append(
                        (
                            wake_comment[1],
                            (match.start() + stripped_sum, match.end() + stripped_sum),
                        )
                    )

                source_code[match.start() : match.end()] = b""
                stripped = match.end() - match.start()

            search_start = match.end() - stripped
            stripped_sum += stripped

        return wake_comments

    @classmethod
    def parse(
        cls, path: Path, ignore_errors: bool = False
    ) -> Tuple[
        SolidityVersionRanges,
        List[str],
        bytes,
        bytes,
        Dict[str, List[Tuple[List[str], Tuple[int, int]]]],
    ]:
        """
        Return a tuple of two lists. The first list contains Solidity version ranges that can be used to compile
        the given file. The second list contains filenames / URLs that are imported from the given file.
        """
        raw_content = path.read_bytes()
        h = BLAKE2b.new(data=raw_content, digest_bits=256)

        # strip all comments, parse wake comments
        stripped_content = bytearray(raw_content)
        wake_comments = cls.strip_comments(stripped_content)

        return (
            cls._parse_version_pragma(stripped_content, ignore_errors),
            cls._parse_import(stripped_content, ignore_errors),
            h.digest(),
            raw_content,
            wake_comments,
        )

    @classmethod
    def parse_source(
        cls,
        source_code: bytes,
        ignore_errors: bool = False,
    ) -> Tuple[
        SolidityVersionRanges,
        List[str],
        bytes,
        Dict[str, List[Tuple[List[str], Tuple[int, int]]]],
    ]:
        """
        Return a tuple of two lists. The first list contains Solidity version ranges that can be used to compile
        the given file. The second list contains filenames / URLs that are imported from the given file.
        """
        h = BLAKE2b.new(data=source_code, digest_bits=256)

        # strip all comments, parse wake comments
        stripped_source_code = bytearray(source_code)
        wake_comments = cls.strip_comments(stripped_source_code)

        return (
            cls._parse_version_pragma(stripped_source_code, ignore_errors),
            cls._parse_import(stripped_source_code, ignore_errors),
            h.digest(),
            wake_comments,
        )
