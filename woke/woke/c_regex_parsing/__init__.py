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


class SolidityVersionRange:
    """
    A class representing a range of Solidity versions by keeping the lower and the higher bound.
    Both bounds can be inclusive or non-inclusive.
    In case the lower bound is unspecified, the default value 0.0.0 (inclusive) is used.
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

        if lower_bound is None:
            self.__lower = SolidityVersion("0.0.0")
        else:
            self.__lower = SolidityVersion(str(lower_bound))
        self.__lower_inclusive = True if lower_inclusive is None else lower_inclusive

        if higher_bound is None:
            self.__higher = None
        else:
            self.__higher = SolidityVersion(str(higher_bound))

            if self.__lower > self.__higher:
                raise ValueError(
                    "The lower bound must be less than or equal to the higher bound."
                )
            elif self.__lower == self.__higher and (
                not lower_inclusive or not higher_inclusive
            ):
                raise ValueError(
                    "In case the lower and the higher bounds are equal, both must be inclusive."
                )

        self.__higher_inclusive = higher_inclusive

    def __contains__(self, item):
        if isinstance(item, str):
            item = SolidityVersion(item)
        if not isinstance(item, SolidityVersion):
            return NotImplemented
        lower_check = (
            item >= self.__lower if self.__lower_inclusive else item > self.__lower
        )
        if not lower_check or self.__higher is None:
            return lower_check
        higher_check = (
            item <= self.__higher if self.__higher_inclusive else item < self.__higher
        )
        return lower_check and higher_check

    def __hash__(self):
        return hash(
            (
                self.__lower,
                self.__lower_inclusive,
                self.__higher,
                self.__higher_inclusive,
            )
        )

    def __eq__(self, other):
        if not isinstance(other, SolidityVersionRange):
            return NotImplemented
        self_attr = (
            self.__lower,
            self.__lower_inclusive,
            self.__higher,
            self.__higher_inclusive,
        )
        other_attr = (
            other.__lower,
            other.__lower_inclusive,
            other.__higher,
            other.__higher_inclusive,
        )
        return self_attr == other_attr

    def __str__(self):
        s = f"{'>=' if self.__lower_inclusive else '>'}{self.__lower}"
        if self.__higher is not None:
            s = s + f" {'<=' if self.__higher_inclusive else '<'}{self.__higher}"
        return s

    def __repr__(self):
        lower = '"' + str(self.__lower) + '"'
        higher = '"' + str(self.__higher) + '"' if self.__higher is not None else None
        return f"{self.__class__.__name__}({lower}, {self.__lower_inclusive}, {higher}, {self.__higher_inclusive})"
