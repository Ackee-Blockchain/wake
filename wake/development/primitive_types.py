from typing import List, Optional, TypeVar

from typing_extensions import Annotated


class ValueRange:
    _min: int
    _max: int

    def __init__(self, min: int, max: int):
        self._min = min
        self._max = max

    @property
    def min(self) -> int:
        return self._min

    @property
    def max(self) -> int:
        return self._max


class Length:
    _length: int

    def __init__(self, length: int):
        self._length = length

    @property
    def length(self) -> int:
        return self._length


NoneType = type(None)


uint8 = Annotated[int, ValueRange(0, 2**8 - 1)]
uint16 = Annotated[int, ValueRange(0, 2**16 - 1)]
uint24 = Annotated[int, ValueRange(0, 2**24 - 1)]
uint32 = Annotated[int, ValueRange(0, 2**32 - 1)]
uint40 = Annotated[int, ValueRange(0, 2**40 - 1)]
uint48 = Annotated[int, ValueRange(0, 2**48 - 1)]
uint56 = Annotated[int, ValueRange(0, 2**56 - 1)]
uint64 = Annotated[int, ValueRange(0, 2**64 - 1)]
uint72 = Annotated[int, ValueRange(0, 2**72 - 1)]
uint80 = Annotated[int, ValueRange(0, 2**80 - 1)]
uint88 = Annotated[int, ValueRange(0, 2**88 - 1)]
uint96 = Annotated[int, ValueRange(0, 2**96 - 1)]
uint104 = Annotated[int, ValueRange(0, 2**104 - 1)]
uint112 = Annotated[int, ValueRange(0, 2**112 - 1)]
uint120 = Annotated[int, ValueRange(0, 2**120 - 1)]
uint128 = Annotated[int, ValueRange(0, 2**128 - 1)]
uint136 = Annotated[int, ValueRange(0, 2**136 - 1)]
uint144 = Annotated[int, ValueRange(0, 2**144 - 1)]
uint152 = Annotated[int, ValueRange(0, 2**152 - 1)]
uint160 = Annotated[int, ValueRange(0, 2**160 - 1)]
uint168 = Annotated[int, ValueRange(0, 2**168 - 1)]
uint176 = Annotated[int, ValueRange(0, 2**176 - 1)]
uint184 = Annotated[int, ValueRange(0, 2**184 - 1)]
uint192 = Annotated[int, ValueRange(0, 2**192 - 1)]
uint200 = Annotated[int, ValueRange(0, 2**200 - 1)]
uint208 = Annotated[int, ValueRange(0, 2**208 - 1)]
uint216 = Annotated[int, ValueRange(0, 2**216 - 1)]
uint224 = Annotated[int, ValueRange(0, 2**224 - 1)]
uint232 = Annotated[int, ValueRange(0, 2**232 - 1)]
uint240 = Annotated[int, ValueRange(0, 2**240 - 1)]
uint248 = Annotated[int, ValueRange(0, 2**248 - 1)]
uint256 = Annotated[int, ValueRange(0, 2**256 - 1)]
uint = uint256

int8 = Annotated[int, ValueRange(-(2**7), 2**7 - 1)]
int16 = Annotated[int, ValueRange(-(2**15), 2**15 - 1)]
int24 = Annotated[int, ValueRange(-(2**23), 2**23 - 1)]
int32 = Annotated[int, ValueRange(-(2**31), 2**31 - 1)]
int40 = Annotated[int, ValueRange(-(2**39), 2**39 - 1)]
int48 = Annotated[int, ValueRange(-(2**47), 2**47 - 1)]
int56 = Annotated[int, ValueRange(-(2**55), 2**55 - 1)]
int64 = Annotated[int, ValueRange(-(2**63), 2**63 - 1)]
int72 = Annotated[int, ValueRange(-(2**71), 2**71 - 1)]
int80 = Annotated[int, ValueRange(-(2**79), 2**79 - 1)]
int88 = Annotated[int, ValueRange(-(2**87), 2**87 - 1)]
int96 = Annotated[int, ValueRange(-(2**95), 2**95 - 1)]
int104 = Annotated[int, ValueRange(-(2**103), 2**103 - 1)]
int112 = Annotated[int, ValueRange(-(2**111), 2**111 - 1)]
int120 = Annotated[int, ValueRange(-(2**119), 2**119 - 1)]
int128 = Annotated[int, ValueRange(-(2**127), 2**127 - 1)]
int136 = Annotated[int, ValueRange(-(2**135), 2**135 - 1)]
int144 = Annotated[int, ValueRange(-(2**143), 2**143 - 1)]
int152 = Annotated[int, ValueRange(-(2**151), 2**151 - 1)]
int160 = Annotated[int, ValueRange(-(2**159), 2**159 - 1)]
int168 = Annotated[int, ValueRange(-(2**167), 2**167 - 1)]
int176 = Annotated[int, ValueRange(-(2**175), 2**175 - 1)]
int184 = Annotated[int, ValueRange(-(2**183), 2**183 - 1)]
int192 = Annotated[int, ValueRange(-(2**191), 2**191 - 1)]
int200 = Annotated[int, ValueRange(-(2**199), 2**199 - 1)]
int208 = Annotated[int, ValueRange(-(2**207), 2**207 - 1)]
int216 = Annotated[int, ValueRange(-(2**215), 2**215 - 1)]
int224 = Annotated[int, ValueRange(-(2**223), 2**223 - 1)]
int232 = Annotated[int, ValueRange(-(2**231), 2**231 - 1)]
int240 = Annotated[int, ValueRange(-(2**239), 2**239 - 1)]
int248 = Annotated[int, ValueRange(-(2**247), 2**247 - 1)]
int256 = Annotated[int, ValueRange(-(2**255), 2**255 - 1)]


bytes1 = Annotated[bytes, Length(1)]
bytes2 = Annotated[bytes, Length(2)]
bytes3 = Annotated[bytes, Length(3)]
bytes4 = Annotated[bytes, Length(4)]
bytes5 = Annotated[bytes, Length(5)]
bytes6 = Annotated[bytes, Length(6)]
bytes7 = Annotated[bytes, Length(7)]
bytes8 = Annotated[bytes, Length(8)]
bytes9 = Annotated[bytes, Length(9)]
bytes10 = Annotated[bytes, Length(10)]
bytes11 = Annotated[bytes, Length(11)]
bytes12 = Annotated[bytes, Length(12)]
bytes13 = Annotated[bytes, Length(13)]
bytes14 = Annotated[bytes, Length(14)]
bytes15 = Annotated[bytes, Length(15)]
bytes16 = Annotated[bytes, Length(16)]
bytes17 = Annotated[bytes, Length(17)]
bytes18 = Annotated[bytes, Length(18)]
bytes19 = Annotated[bytes, Length(19)]
bytes20 = Annotated[bytes, Length(20)]
bytes21 = Annotated[bytes, Length(21)]
bytes22 = Annotated[bytes, Length(22)]
bytes23 = Annotated[bytes, Length(23)]
bytes24 = Annotated[bytes, Length(24)]
bytes25 = Annotated[bytes, Length(25)]
bytes26 = Annotated[bytes, Length(26)]
bytes27 = Annotated[bytes, Length(27)]
bytes28 = Annotated[bytes, Length(28)]
bytes29 = Annotated[bytes, Length(29)]
bytes30 = Annotated[bytes, Length(30)]
bytes31 = Annotated[bytes, Length(31)]
bytes32 = Annotated[bytes, Length(32)]


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
