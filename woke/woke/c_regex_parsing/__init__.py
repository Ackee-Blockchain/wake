from typing import Optional, Union
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

    def __init__(
        self,
        major: int,
        minor: int,
        patch: int,
        prerelease: Optional[str] = None,
        build: Optional[str] = None,
    ):
        self.__major = major
        self.__minor = minor
        self.__patch = patch
        self.__prerelease = prerelease
        self.__build = build

    def __str__(self):
        s = f"{self.major}.{self.minor}.{self.patch}"
        if self.__prerelease is not None:
            s += f"-{self.__prerelease}"
        if self.__build is not None:
            s += f"+{self.__build}"
        return s

    def __repr__(self):
        prerelease = (
            '"' + self.__prerelease + '"' if self.__prerelease is not None else None
        )
        build = '"' + self.__build + '"' if self.__build is not None else None
        return f"{self.__class__.__name__}({self.major}, {self.minor}, {self.patch}, {prerelease}, {build})"

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

    @classmethod
    def fromstring(cls, version_str: str) -> "SolidityVersion":
        match = cls.RE.match(version_str)
        if not match:
            raise ValueError(f"Invalid Solidity version: {version_str}")
        groups = match.groups()
        major = int(groups[0])
        minor = int(groups[1])
        patch = int(groups[2])
        prerelease = None if groups[3] is None else groups[3][1:]
        build = None if groups[4] is None else groups[4][1:]
        return SolidityVersion(major, minor, patch, prerelease, build)

    @property
    def major(self):
        return self.__major

    @property
    def minor(self):
        return self.__minor

    @property
    def patch(self):
        return self.__patch


class SolidityVersionRange:
    """
    A class representing a range of Solidity versions by keeping the lower and the higher bound.
    Both bounds can be inclusive or non-inclusive.
    In case the lower bound is unspecified, the default value 0.0.0 (inclusive) is used.
    If the lower bound is semantically greater than the higher bound, create an empty range.
    """

    __lower: SolidityVersion
    __lower_inclusive: bool
    __higher: Optional[SolidityVersion]
    __higher_inclusive: Optional[bool]

    def __init__(
        self,
        lower_bound: Optional[Union[SolidityVersion, str]],
        lower_inclusive: Optional[bool],
        higher_bound: Optional[Union[SolidityVersion, str]],
        higher_inclusive: Optional[bool],
    ):
        if (lower_bound is None) != (lower_inclusive is None):
            raise ValueError(
                "Both arguments lower_bound and lower_inclusive must be either set or unset."
            )
        if (higher_bound is None) != (higher_inclusive is None):
            raise ValueError(
                "Both arguments higher_bound and higher_inclusive must be either set or unset."
            )

        self.__lower_inclusive = True if lower_inclusive is None else lower_inclusive
        if lower_bound is None:
            self.__lower = SolidityVersion(0, 0, 0)
        else:
            self.__lower = SolidityVersion.fromstring(str(lower_bound))

        self.__higher_inclusive = higher_inclusive
        if higher_bound is None:
            self.__higher = None
        else:
            self.__higher = SolidityVersion.fromstring(str(higher_bound))

            if (
                self.lower > self.higher
                or self.lower == self.higher
                and (not lower_inclusive or not higher_inclusive)
            ):
                # create an empty range
                self.__lower = SolidityVersion(0, 0, 0)
                self.__lower_inclusive = False
                self.__higher = self.lower
                self.__higher_inclusive = False

    def __contains__(self, item):
        if isinstance(item, str):
            item = SolidityVersion.fromstring(item)
        if not isinstance(item, SolidityVersion):
            return NotImplemented
        if self.isempty():
            return False

        lower_check = item >= self.lower if self.lower_inclusive else item > self.lower
        if not lower_check or self.higher is None:
            return lower_check
        higher_check = (
            item <= self.higher if self.higher_inclusive else item < self.higher
        )
        return lower_check and higher_check

    def __hash__(self):
        return hash(
            (
                self.lower,
                self.lower_inclusive,
                self.higher,
                self.higher_inclusive,
            )
        )

    def __eq__(self, other):
        if not isinstance(other, SolidityVersionRange):
            return NotImplemented
        self_attr = (
            self.lower,
            self.lower_inclusive,
            self.higher,
            self.higher_inclusive,
        )
        other_attr = (
            other.lower,
            other.lower_inclusive,
            other.higher,
            other.higher_inclusive,
        )
        return self_attr == other_attr

    def __str__(self):
        s = f"{'>=' if self.lower_inclusive else '>'}{self.lower}"
        if self.higher is not None:
            s = s + f" {'<=' if self.higher_inclusive else '<'}{self.higher}"
        return s

    def __repr__(self):
        lower = '"' + str(self.lower) + '"'
        higher = '"' + str(self.higher) + '"' if self.higher is not None else None
        return f"{self.__class__.__name__}({lower}, {self.lower_inclusive}, {higher}, {self.higher_inclusive})"

    def __and__(self, other: "SolidityVersionRange") -> "SolidityVersionRange":
        if self.lower < other.lower:
            lower_bound = other.lower
            lower_inclusive = other.lower_inclusive
        elif self.lower > other.lower:
            lower_bound = self.lower
            lower_inclusive = self.lower_inclusive
        else:
            lower_bound = self.lower
            if not self.lower_inclusive:
                lower_inclusive = self.lower_inclusive
            else:
                lower_inclusive = other.lower_inclusive

        if self.higher is None:
            higher_bound = other.higher
            higher_inclusive = other.higher_inclusive
        elif other.higher is None:
            higher_bound = self.higher
            higher_inclusive = self.higher_inclusive
        else:
            if self.higher < other.higher:
                higher_bound = self.higher
                higher_inclusive = self.higher_inclusive
            elif self.higher > other.higher:
                higher_bound = other.higher
                higher_inclusive = other.higher_inclusive
            else:
                higher_bound = self.higher
                if not self.higher_inclusive:
                    higher_inclusive = self.higher_inclusive
                else:
                    higher_inclusive = other.higher_inclusive

        return SolidityVersionRange(
            lower_bound, lower_inclusive, higher_bound, higher_inclusive
        )

    @classmethod
    def intersection(cls, *args: "SolidityVersionRange") -> "SolidityVersionRange":
        ret = cls(None, None, None, None)
        for r in args:
            ret &= r
        return ret

    def isempty(self) -> bool:
        return (
            self.lower == SolidityVersion(0, 0, 0)
            and not self.lower_inclusive
            and self.higher == SolidityVersion(0, 0, 0)
            and not self.higher_inclusive
        )

    @property
    def lower(self):
        return self.__lower

    @property
    def lower_inclusive(self):
        return self.__lower_inclusive

    @property
    def higher(self):
        return self.__higher

    @property
    def higher_inclusive(self):
        return self.__higher_inclusive
