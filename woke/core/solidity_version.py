import itertools
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, Iterable, Optional, Tuple, Union

"""
This module implements semantic version (and `npm` semantic version range) parsing as described
by `NPM semver <https://www.npmjs.com/package/semver>`_ and `solc source code <https://github.com/ethereum/solidity/blob/55467c1ccaffd5fcf6ea988d5e091d468a08f533/liblangutil/SemVerHandler.cpp>`_.
As these two implementations are not compatible, some compromises have been made. These include:
* A version cannot start with `v` prefix.
* Partial versions that do not represent a range are not supported. These are e.g. `x.1.2`, `0.X.7` or `*.*.3`.
* Whitespace between a partial expression and operator are permitted. `>= 1.2.3 <= 7.8.9`, `1.2.3 \t-\r\n 4.5.6` are valid expressions.
* Version prereleases and build strings are ignored in comparison.
* A hyphen range cannot include additional operators. Expressions `>=1.2.3 - <=4.5.6` or `~1.2.3 - ^4.5.6` are not permitted.
"""


class VersionAbc(ABC):
    @abstractmethod
    def __str__(self):
        ...

    @abstractmethod
    def __hash__(self):
        ...

    @abstractmethod
    def __eq__(self, other):
        ...

    @abstractmethod
    def __lt__(self, other):
        ...

    @abstractmethod
    def __le__(self, other):
        ...

    @abstractmethod
    def __gt__(self, other):
        ...

    @abstractmethod
    def __ge__(self, other):
        ...

    @classmethod
    @abstractmethod
    def fromstring(cls, version_str: str) -> "VersionAbc":
        ...

    @classmethod
    def validate(cls, v):
        if isinstance(v, VersionAbc):
            return v
        if isinstance(v, str):
            return cls.fromstring(v)
        raise TypeError()

    @classmethod
    def __get_validators__(cls):
        yield cls.validate


class SolidityVersion(VersionAbc):
    """
    A class representing a single Solidity version (not a range of versions).
    Prerelease and build tags are parsed but ignored (even in comparison). As of `solc` version 0.8.11 there is no use for them.
    """

    NUMBER = r"0|[1-9][0-9]*"
    PRERELEASE_OR_BUILD_PART = r"[-0-9A-Za-z]+"
    PRERELEASE_OR_BUILD = r"{part}(?:\.{part})*".format(part=PRERELEASE_OR_BUILD_PART)
    RE = re.compile(
        r"^(?P<major>{number})\.(?P<minor>{number})\.(?P<patch>{number})(?:-(?P<prerelease>{prerelease}))?(?:\+(?P<build>{build}))?$".format(
            number=NUMBER, prerelease=PRERELEASE_OR_BUILD, build=PRERELEASE_OR_BUILD
        )
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

    def __str__(self) -> str:
        s = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease is not None:
            s += f"-{self.prerelease}"
        if self.build is not None:
            s += f"+{self.build}"
        return s

    def __repr__(self) -> str:
        prerelease = (
            '"' + self.prerelease + '"' if self.prerelease is not None else None
        )
        build = '"' + self.build + '"' if self.build is not None else None
        return f"{self.__class__.__name__}({self.major}, {self.minor}, {self.patch}, {prerelease}, {build})"

    def __hash__(self) -> int:
        return hash((self.major, self.minor, self.patch))

    def __eq__(self, other) -> bool:
        cls = self.__class__

        if isinstance(other, str):
            other = cls.fromstring(other)
        elif not isinstance(other, cls):
            return NotImplemented
        return (
            self.major == other.major
            and self.minor == other.minor
            and self.patch == other.patch
        )

    def __lt__(self, other) -> bool:
        cls = self.__class__

        if isinstance(other, str):
            other = cls.fromstring(other)
        elif not isinstance(other, self.__class__):
            return NotImplemented
        return (self.major, self.minor, self.patch) < (
            other.major,
            other.minor,
            other.patch,
        )

    def __le__(self, other) -> bool:
        return self < other or self == other

    def __gt__(self, other):
        lt = self < other
        if lt is NotImplemented:
            return NotImplemented
        return not lt and self != other

    def __ge__(self, other):
        lt = self < other
        if lt is NotImplemented:
            return NotImplemented
        return not lt

    @classmethod
    def fromstring(cls, version_str: str) -> "SolidityVersion":
        match = cls.RE.match(version_str)
        if not match:
            raise ValueError(f"Invalid Solidity version: `{version_str}`")
        groups = match.groupdict()
        major = int(groups["major"])
        minor = int(groups["minor"])
        patch = int(groups["patch"])
        prerelease = groups["prerelease"]
        build = groups["build"]
        return SolidityVersion(major, minor, patch, prerelease, build)

    @property
    def major(self) -> int:
        return self.__major

    @property
    def minor(self) -> int:
        return self.__minor

    @property
    def patch(self) -> int:
        return self.__patch

    @property
    def prerelease(self) -> Optional[str]:
        return self.__prerelease

    @property
    def build(self) -> Optional[str]:
        return self.__build


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

    def __contains__(self, item) -> bool:
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

    def __hash__(self) -> int:
        return hash(
            (
                self.lower,
                self.lower_inclusive,
                self.higher,
                self.higher_inclusive,
            )
        )

    def __eq__(self, other) -> bool:
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

    def __str__(self) -> str:
        s = f"{'>=' if self.lower_inclusive else '>'}{self.lower}"
        if self.higher is not None:
            s = s + f" {'<=' if self.higher_inclusive else '<'}{self.higher}"
        return s

    def __repr__(self) -> str:
        lower = '"' + str(self.lower) + '"'
        higher = '"' + str(self.higher) + '"' if self.higher is not None else None
        return f"{self.__class__.__name__}({lower}, {self.lower_inclusive}, {higher}, {self.higher_inclusive})"

    def __and__(self, other: "SolidityVersionRange") -> "SolidityVersionRange":
        """
        Perform an intersection of two Solidity version ranges and return a new instance of `SolidityVersionRange`.
        """
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
        """
        Perform an intersection of all `SolidityVersionRange` arguments and return a new instance of `SolidityVersionRange`.
        """
        ret = cls(None, None, None, None)
        for r in args:
            ret &= r
        return ret

    def isempty(self) -> bool:
        """
        Return `True` if the range is empty (no Solidity version can be contained in this range), `False` otherwise.
        """
        return (
            self.lower == SolidityVersion(0, 0, 0)
            and not self.lower_inclusive
            and self.higher == SolidityVersion(0, 0, 0)
            and not self.higher_inclusive
        )

    @property
    def lower(self) -> SolidityVersion:
        return self.__lower

    @property
    def lower_inclusive(self) -> bool:
        return self.__lower_inclusive

    @property
    def higher(self) -> Optional[SolidityVersion]:
        return self.__higher

    @property
    def higher_inclusive(self) -> Optional[bool]:
        return self.__higher_inclusive


class SolidityVersionRanges:
    """
    Helper class implementing intersection on List[SolidityVersionRange].
    """

    __version_ranges: Tuple[SolidityVersionRange]

    def __init__(self, version_ranges: Iterable[SolidityVersionRange]):
        self.__version_ranges = tuple(version_ranges)

    def __and__(self, other):
        if not isinstance(other, SolidityVersionRanges):
            return NotImplemented
        ret = []
        for r1, r2 in itertools.product(self.version_ranges, other.version_ranges):
            new_range = r1 & r2
            if not new_range.isempty():
                ret.append(new_range)
        return SolidityVersionRanges(ret)

    def __iter__(self):
        for version_range in self.__version_ranges:
            yield version_range

    def __len__(self):
        return len(self.__version_ranges)

    def __str__(self):
        return " || ".join(
            str(version_range) for version_range in self.__version_ranges
        )

    def __contains__(self, item):
        if isinstance(item, str):
            item = SolidityVersion.fromstring(item)
        if not isinstance(item, SolidityVersion):
            return NotImplemented
        return any(item in version_range for version_range in self.__version_ranges)

    @property
    def version_ranges(self) -> Tuple[SolidityVersionRange]:
        return self.__version_ranges


class SolidityVersionExpr:
    ERROR_MSG = r"Invalid Solidity version expression: `{value}`"
    NUMBER = r"x|X|\*|0|[1-9][0-9]*"
    PARTIAL = r"(?P<major>{number})\s*(?:\.\s*(?P<minor>{number}))?\s*(?:\.\s*(?P<patch>{number}))?".format(
        number=NUMBER
    )
    PARTIAL_RE = re.compile(r"^\s*{partial}\s*$".format(partial=PARTIAL))
    PART = r"(?P<operator>\^|~|<|<=|>|>=|=)?\s*{partial}".format(partial=PARTIAL)
    RANGE_RE = re.compile(r"\s*{part}\s*".format(part=PART))
    RANGES_RE = re.compile(r"^(\s*{part}\s*)+$".format(part=PART))

    __expression: str
    __ranges: SolidityVersionRanges

    def __init__(self, expr: str):
        cls = self.__class__
        self.__expression = expr
        evaluated_ranges = []

        ranges = expr.split("||")
        for r in ranges:
            if "-" in r:
                evaluated_ranges.append(cls.__parse_hyphen_range(r))
            else:
                evaluated_ranges.append(cls.__parse_range(r))
        self.__ranges = SolidityVersionRanges(evaluated_ranges)

    @classmethod
    def __parse_range(cls, range_str: str) -> SolidityVersionRange:
        check = cls.RANGES_RE.match(range_str)
        if not check:
            raise ValueError(cls.ERROR_MSG.format(value=range_str))

        matches = cls.RANGE_RE.finditer(range_str)
        ret = SolidityVersionRange(None, None, None, None)
        for match in matches:
            ret &= cls.__parse_simple(match.groupdict(), match.string.strip())
        return ret

    @classmethod
    def __parse_hyphen_range(cls, hyphen_range: str) -> SolidityVersionRange:
        partials = hyphen_range.split("-")
        if len(partials) != 2:
            raise ValueError(cls.ERROR_MSG.format(value=hyphen_range))
        match_left = cls.PARTIAL_RE.match(partials[0])
        match_right = cls.PARTIAL_RE.match(partials[1])
        if not match_left or not match_right:
            raise ValueError(cls.ERROR_MSG.format(value=hyphen_range))

        partial_left = cls.__parse_partial(
            match_left.groupdict(), match_left.string.strip()
        )
        left = cls.__evaluate_ge(*partial_left)
        partial_right = cls.__parse_partial(
            match_right.groupdict(), match_right.string.strip()
        )
        right = cls.__evaluate_le(*partial_right, match_right.string.strip())
        return left & right

    @classmethod
    def __parse_partial(
        cls, match_dict: Dict[str, Any], match_str: str
    ) -> Tuple[Optional[int], Optional[int], Optional[int]]:
        major = match_dict["major"]
        minor = match_dict["minor"]
        patch = match_dict["patch"]
        if major in {None, "x", "X", "*"}:
            major = None
        else:
            major = int(major)
        if minor in {None, "x", "X", "*"}:
            minor = None
        else:
            minor = int(minor)
        if patch in {None, "x", "X", "*"}:
            patch = None
        else:
            patch = int(patch)

        # partials should be in ascending order, i.e.: 1.0.x, 1.x.x, x.x.x, not x.0.1 or 1.x.5
        if (major is None and not all(x is None for x in (minor, patch))) or (
            minor is None and patch is not None
        ):
            raise ValueError(cls.ERROR_MSG.format(value=match_str))

        return major, minor, patch

    @classmethod
    def __evaluate_caret(
        cls,
        major: Optional[int],
        minor: Optional[int],
        patch: Optional[int],
        match_str: str,
    ) -> SolidityVersionRange:
        if major is None:
            raise ValueError(cls.ERROR_MSG.format(value=match_str))
        elif minor is None:
            # ^1.x.x := >=1.0.0 < 2.0.0
            v1 = SolidityVersion(major, 0, 0)
            v2 = SolidityVersion(major + 1, 0, 0)
            return SolidityVersionRange(v1, True, v2, False)
        elif patch is None:
            if major != 0:
                # ^1.2.x := >=1.2.0 < 2.0.0
                v1 = SolidityVersion(major, minor, 0)
                v2 = SolidityVersion(major + 1, 0, 0)
                return SolidityVersionRange(v1, True, v2, False)
            else:
                # ^0.2.x := >=0.2.0 <0.3.0
                # ^0.0.x := >=0.0.0 <0.1.0
                v1 = SolidityVersion(major, minor, 0)
                v2 = SolidityVersion(major, minor + 1, 0)
                return SolidityVersionRange(v1, True, v2, False)
        elif major != 0:
            # ^1.2.3 := >=1.2.3 <2.0.0
            v1 = SolidityVersion(major, minor, patch)
            v2 = SolidityVersion(major + 1, 0, 0)
            return SolidityVersionRange(v1, True, v2, False)
        elif minor != 0:
            # ^0.2.3 := >=0.2.3 <0.3.0
            v1 = SolidityVersion(major, minor, patch)
            v2 = SolidityVersion(major, minor + 1, 0)
            return SolidityVersionRange(v1, True, v2, False)
        elif patch != 0:
            # ^0.0.3 := >=0.0.3 <0.0.4
            v1 = SolidityVersion(major, minor, patch)
            v2 = SolidityVersion(major, minor, patch + 1)
            return SolidityVersionRange(v1, True, v2, False)
        else:
            raise ValueError(cls.ERROR_MSG.format(value=match_str))

    @classmethod
    def __evaluate_tilde(
        cls,
        major: Optional[int],
        minor: Optional[int],
        patch: Optional[int],
        match_str: str,
    ) -> SolidityVersionRange:
        if major is None:
            raise ValueError(cls.ERROR_MSG.format(value=match_str))
        elif minor is None:
            # ~1.x.x := >=1.0.0 <2.0.0
            v1 = SolidityVersion(major, 0, 0)
            v2 = SolidityVersion(major + 1, 0, 0)
            return SolidityVersionRange(v1, True, v2, False)
        elif patch is None:
            # ~1.2.x := >=1.2.0 <1.3.0
            v1 = SolidityVersion(major, minor, 0)
            v2 = SolidityVersion(major, minor + 1, 0)
            return SolidityVersionRange(v1, True, v2, False)
        else:
            # ~1.2.3 := >=1.2.3 <1.3.0
            v1 = SolidityVersion(major, minor, patch)
            v2 = SolidityVersion(major, minor + 1, 0)
            return SolidityVersionRange(v1, True, v2, False)

    @classmethod
    def __evaluate_lt(
        cls,
        major: Optional[int],
        minor: Optional[int],
        patch: Optional[int],
        match_str: str,
    ) -> SolidityVersionRange:
        if major is None:
            raise ValueError(cls.ERROR_MSG.format(value=match_str))
        # <1.x.x := <1.0.0
        # <1.2.x := <1.2.0
        # <1.2.3 := <1.2.3
        v2 = SolidityVersion(major, minor or 0, patch or 0)
        return SolidityVersionRange(None, None, v2, False)

    @classmethod
    def __evaluate_le(
        cls,
        major: Optional[int],
        minor: Optional[int],
        patch: Optional[int],
        match_str: str,
    ) -> SolidityVersionRange:
        if major is None:
            raise ValueError(cls.ERROR_MSG.format(value=match_str))
        elif minor is None:
            # <=1.x.x := <2.0.0
            v2 = SolidityVersion(major + 1, 0, 0)
            return SolidityVersionRange(None, None, v2, False)
        elif patch is None:
            # <=1.2.x := <1.3.0
            v2 = SolidityVersion(major, minor + 1, 0)
            return SolidityVersionRange(None, None, v2, False)
        else:
            # <=1.2.3 := <=1.2.3
            v2 = SolidityVersion(major, minor, patch)
            return SolidityVersionRange(None, None, v2, True)

    @classmethod
    def __evaluate_gt(
        cls,
        major: Optional[int],
        minor: Optional[int],
        patch: Optional[int],
        match_str: str,
    ) -> SolidityVersionRange:
        if major is None:
            raise ValueError(cls.ERROR_MSG.format(value=match_str))
        elif minor is None:
            # >1.x.x := >=2.0.0
            v1 = SolidityVersion(major + 1, 0, 0)
            return SolidityVersionRange(v1, True, None, None)
        elif patch is None:
            # >1.2.x := >=1.3.0
            v1 = SolidityVersion(major, minor + 1, 0)
            return SolidityVersionRange(v1, True, None, None)
        else:
            # >1.2.3 := >1.2.3
            v1 = SolidityVersion(major, minor, patch)
            return SolidityVersionRange(v1, False, None, None)

    @classmethod
    def __evaluate_ge(
        cls, major: Optional[int], minor: Optional[int], patch: Optional[int]
    ) -> SolidityVersionRange:
        # >=x.x.x := >=0.0.0
        # >=1.x.x := >=1.0.0
        # >=1.2.x := >=1.2.0
        # >=1.2.3 := >=1.2.3
        v1 = SolidityVersion(major or 0, minor or 0, patch or 0)
        return SolidityVersionRange(v1, True, None, None)

    @classmethod
    def __evaluate_eq(
        cls, major: Optional[int], minor: Optional[int], patch: Optional[int]
    ) -> SolidityVersionRange:
        # x.x.x := >=0.0.0
        if major is None:
            return SolidityVersionRange("0.0.0", True, None, None)
        # 1.x.x := >=1.0.0 <2.0.0
        elif minor is None:
            v1 = SolidityVersion(major, 0, 0)
            v2 = SolidityVersion(major + 1, 0, 0)
            return SolidityVersionRange(v1, True, v2, False)
        # 1.2.x := >=1.2.0 <1.3.0
        elif patch is None:
            v1 = SolidityVersion(major, minor, 0)
            v2 = SolidityVersion(major, minor + 1, 0)
            return SolidityVersionRange(v1, True, v2, False)
        # 1.2.3 := >=1.2.3 <=1.2.3
        else:
            v = SolidityVersion(major, minor, patch)
            return SolidityVersionRange(v, True, v, True)

    @classmethod
    def __parse_simple(cls, match_dict: dict, match_str: str) -> SolidityVersionRange:
        operator: Optional[str] = match_dict["operator"]
        major, minor, patch = cls.__parse_partial(match_dict, match_str)

        if operator == "^":
            return cls.__evaluate_caret(major, minor, patch, match_str)
        elif operator == "~":
            return cls.__evaluate_tilde(major, minor, patch, match_str)
        elif operator == "<":
            return cls.__evaluate_lt(major, minor, patch, match_str)
        elif operator == "<=":
            return cls.__evaluate_le(major, minor, patch, match_str)
        elif operator == ">":
            return cls.__evaluate_gt(major, minor, patch, match_str)
        elif operator == ">=":
            return cls.__evaluate_ge(major, minor, patch)
        elif operator == "=" or operator is None:
            return cls.__evaluate_eq(major, minor, patch)
        else:
            raise ValueError(cls.ERROR_MSG.format(value=match_str))

    def __contains__(self, item) -> bool:
        if isinstance(item, str):
            item = SolidityVersion.fromstring(item)
        if not isinstance(item, SolidityVersion):
            return NotImplemented
        for r in self.__ranges:
            if item in r:
                return True
        return False

    def __str__(self) -> str:
        return self.__expression

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}("{str(self)}")'

    @property
    def version_ranges(self) -> SolidityVersionRanges:
        return self.__ranges
