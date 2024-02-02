import re
from pathlib import Path

from wake.core.solidity_version import (
    SolidityVersionExpr,
    SolidityVersionRange,
    SolidityVersionRanges,
)

VyperVersionExpr = SolidityVersionExpr
VyperVersionRange = SolidityVersionRange
VyperVersionRanges = SolidityVersionRanges


class VyperSourceParser:
    PRAGMA_VYPER_RE = re.compile(rb"#\s+@version\s+(?P<version>.+)")

    @classmethod
    def _parse_version_pragma(
        cls, source_code: bytes, ignore_errors: bool
    ) -> SolidityVersionRanges:
        versions = None
        matches = cls.PRAGMA_VYPER_RE.finditer(source_code)
        for match in matches:
            version_str = match.groupdict()["version"].strip()
            try:
                version_expr = VyperVersionExpr(version_str.decode("utf-8"))
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
            versions = VyperVersionRanges(
                [VyperVersionRange("0.0.0", True, None, None)]
            )
        return versions


    @classmethod
    def parse(cls, content: bytes) -> VyperVersionRanges:

        return cls._parse_version_pragma(content, ignore_errors=True)
