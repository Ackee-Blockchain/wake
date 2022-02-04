from typing import Optional
from functools import total_ordering
import re


@total_ordering
class SolidityVersion:
    """
    A class representing a single Solidity version (not a range of versions).
    Prerelease and build tags are parsed but ignored (even in comparison). As of `solc` version 0.8.11 there is no use for them.
    """

    RE = re.compile(
        r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-[^\s+]+)?(\+[^\s]+)?$"
    )
    __major: int
    __minor: int
    __patch: int
    __prerelease: Optional[str]
    __build: Optional[str]

    def __init__(self, version_str: str):
        match = self.__class__.RE.match(version_str)
        if not match:
            raise ValueError(f"Invalid Solidity version: {version_str}")
        groups = match.groups()
        self.__major = int(groups[0])
        self.__minor = int(groups[1])
        self.__patch = int(groups[2])
        self.__prerelease = None if groups[3] is None else groups[3][1:]
        self.__build = None if groups[4] is None else groups[4][1:]

    def __str__(self):
        s = f"{self.major}.{self.minor}.{self.patch}"
        if self.__prerelease is not None:
            s += f"-{self.__prerelease}"
        if self.__build is not None:
            s += f"+{self.__build}"
        return s

    def __repr__(self):
        return f'{self.__class__.__name__}("{str(self)}")'

    def __hash__(self):
        return hash((self.major, self.minor, self.patch))

    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            return NotImplemented
        return (
            self.major == other.major
            and self.minor == other.minor
            and self.patch == other.patch
        )

    def __lt__(self, other):
        if not isinstance(other, self.__class__):
            return NotImplemented
        return (self.major, self.minor, self.patch) < (
            other.major,
            other.minor,
            other.patch,
        )

    @property
    def major(self):
        return self.__major

    @property
    def minor(self):
        return self.__minor

    @property
    def patch(self):
        return self.__patch
