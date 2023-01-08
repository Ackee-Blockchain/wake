from typing import List, NewType, Optional, TypeVar

from typing_extensions import Annotated

uint8 = NewType("uint8", int)
uint16 = NewType("uint16", int)
uint24 = NewType("uint24", int)
uint32 = NewType("uint32", int)
uint40 = NewType("uint40", int)
uint48 = NewType("uint48", int)
uint56 = NewType("uint56", int)
uint64 = NewType("uint64", int)
uint72 = NewType("uint72", int)
uint80 = NewType("uint80", int)
uint88 = NewType("uint88", int)
uint96 = NewType("uint96", int)
uint104 = NewType("uint104", int)
uint112 = NewType("uint112", int)
uint120 = NewType("uint120", int)
uint128 = NewType("uint128", int)
uint136 = NewType("uint136", int)
uint144 = NewType("uint144", int)
uint152 = NewType("uint152", int)
uint160 = NewType("uint160", int)
uint168 = NewType("uint168", int)
uint176 = NewType("uint176", int)
uint184 = NewType("uint184", int)
uint192 = NewType("uint192", int)
uint200 = NewType("uint200", int)
uint208 = NewType("uint208", int)
uint216 = NewType("uint216", int)
uint224 = NewType("uint224", int)
uint232 = NewType("uint232", int)
uint240 = NewType("uint240", int)
uint248 = NewType("uint248", int)
uint256 = NewType("uint256", int)
uint = uint256

int8 = NewType("int8", int)
int16 = NewType("int16", int)
int24 = NewType("int24", int)
int32 = NewType("int32", int)
int40 = NewType("int40", int)
int48 = NewType("int48", int)
int56 = NewType("int56", int)
int64 = NewType("int64", int)
int72 = NewType("int72", int)
int80 = NewType("int80", int)
int88 = NewType("int88", int)
int96 = NewType("int96", int)
int104 = NewType("int104", int)
int112 = NewType("int112", int)
int120 = NewType("int120", int)
int128 = NewType("int128", int)
int136 = NewType("int136", int)
int144 = NewType("int144", int)
int152 = NewType("int152", int)
int160 = NewType("int160", int)
int168 = NewType("int168", int)
int176 = NewType("int176", int)
int184 = NewType("int184", int)
int192 = NewType("int192", int)
int200 = NewType("int200", int)
int208 = NewType("int208", int)
int216 = NewType("int216", int)
int224 = NewType("int224", int)
int232 = NewType("int232", int)
int240 = NewType("int240", int)
int248 = NewType("int248", int)
int256 = NewType("int256", int)

bytes1 = NewType("bytes1", bytes)
bytes2 = NewType("bytes2", bytes)
bytes3 = NewType("bytes3", bytes)
bytes4 = NewType("bytes4", bytes)
bytes5 = NewType("bytes5", bytes)
bytes6 = NewType("bytes6", bytes)
bytes7 = NewType("bytes7", bytes)
bytes8 = NewType("bytes8", bytes)
bytes9 = NewType("bytes9", bytes)
bytes10 = NewType("bytes10", bytes)
bytes11 = NewType("bytes11", bytes)
bytes12 = NewType("bytes12", bytes)
bytes13 = NewType("bytes13", bytes)
bytes14 = NewType("bytes14", bytes)
bytes15 = NewType("bytes15", bytes)
bytes16 = NewType("bytes16", bytes)
bytes17 = NewType("bytes17", bytes)
bytes18 = NewType("bytes18", bytes)
bytes19 = NewType("bytes19", bytes)
bytes20 = NewType("bytes20", bytes)
bytes21 = NewType("bytes21", bytes)
bytes22 = NewType("bytes22", bytes)
bytes23 = NewType("bytes23", bytes)
bytes24 = NewType("bytes24", bytes)
bytes25 = NewType("bytes25", bytes)
bytes26 = NewType("bytes26", bytes)
bytes27 = NewType("bytes27", bytes)
bytes28 = NewType("bytes28", bytes)
bytes29 = NewType("bytes29", bytes)
bytes30 = NewType("bytes30", bytes)
bytes31 = NewType("bytes31", bytes)
bytes32 = NewType("bytes32", bytes)


class Length:
    _min: int
    _max: int

    def __init__(self, a: int, b: Optional[int] = None) -> None:
        if b is None:
            self._min = a
            self._max = a
        else:
            self._min = min(a, b)
            self._max = max(a, b)

    @property
    def min(self) -> int:
        return self._min

    @property
    def max(self) -> int:
        return self._max


T = TypeVar("T")
List1 = Annotated[List[T], Length(1)]
List2 = Annotated[List[T], Length(2)]
List3 = Annotated[List[T], Length(3)]
List4 = Annotated[List[T], Length(4)]
List5 = Annotated[List[T], Length(5)]
List6 = Annotated[List[T], Length(6)]
List7 = Annotated[List[T], Length(7)]
List8 = Annotated[List[T], Length(8)]
List9 = Annotated[List[T], Length(9)]
List10 = Annotated[List[T], Length(10)]
List11 = Annotated[List[T], Length(11)]
List12 = Annotated[List[T], Length(12)]
List13 = Annotated[List[T], Length(13)]
List14 = Annotated[List[T], Length(14)]
List15 = Annotated[List[T], Length(15)]
List16 = Annotated[List[T], Length(16)]
List17 = Annotated[List[T], Length(17)]
List18 = Annotated[List[T], Length(18)]
List19 = Annotated[List[T], Length(19)]
List20 = Annotated[List[T], Length(20)]
List21 = Annotated[List[T], Length(21)]
List22 = Annotated[List[T], Length(22)]
List23 = Annotated[List[T], Length(23)]
List24 = Annotated[List[T], Length(24)]
List25 = Annotated[List[T], Length(25)]
List26 = Annotated[List[T], Length(26)]
List27 = Annotated[List[T], Length(27)]
List28 = Annotated[List[T], Length(28)]
List29 = Annotated[List[T], Length(29)]
List30 = Annotated[List[T], Length(30)]
List31 = Annotated[List[T], Length(31)]
List32 = Annotated[List[T], Length(32)]
