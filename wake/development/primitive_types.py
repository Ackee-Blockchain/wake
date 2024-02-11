import abc
from typing import Iterable, List, TypeVar

NoneType = type(None)


class Integer(int, abc.ABC):
    min: int
    max: int


class uint8(Integer):
    min = 0
    max = 2**8 - 1


class uint16(Integer):
    min = 0
    max = 2**16 - 1


class uint24(Integer):
    min = 0
    max = 2**24 - 1


class uint32(Integer):
    min = 0
    max = 2**32 - 1


class uint40(Integer):
    min = 0
    max = 2**40 - 1


class uint48(Integer):
    min = 0
    max = 2**48 - 1


class uint56(Integer):
    min = 0
    max = 2**56 - 1


class uint64(Integer):
    min = 0
    max = 2**64 - 1


class uint72(Integer):
    min = 0
    max = 2**72 - 1


class uint80(Integer):
    min = 0
    max = 2**80 - 1


class uint88(Integer):
    min = 0
    max = 2**88 - 1


class uint96(Integer):
    min = 0
    max = 2**96 - 1


class uint104(Integer):
    min = 0
    max = 2**104 - 1


class uint112(Integer):
    min = 0
    max = 2**112 - 1


class uint120(Integer):
    min = 0
    max = 2**120 - 1


class uint128(Integer):
    min = 0
    max = 2**128 - 1


class uint136(Integer):
    min = 0
    max = 2**136 - 1


class uint144(Integer):
    min = 0
    max = 2**144 - 1


class uint152(Integer):
    min = 0
    max = 2**152 - 1


class uint160(Integer):
    min = 0
    max = 2**160 - 1


class uint168(Integer):
    min = 0
    max = 2**168 - 1


class uint176(Integer):
    min = 0
    max = 2**176 - 1


class uint184(Integer):
    min = 0
    max = 2**184 - 1


class uint192(Integer):
    min = 0
    max = 2**192 - 1


class uint200(Integer):
    min = 0
    max = 2**200 - 1


class uint208(Integer):
    min = 0
    max = 2**208 - 1


class uint216(Integer):
    min = 0
    max = 2**216 - 1


class uint224(Integer):
    min = 0
    max = 2**224 - 1


class uint232(Integer):
    min = 0
    max = 2**232 - 1


class uint240(Integer):
    min = 0
    max = 2**240 - 1


class uint248(Integer):
    min = 0
    max = 2**248 - 1


class uint256(Integer):
    min = 0
    max = 2**256 - 1


uint = uint256


class int8(Integer):
    min = -(2**7)
    max = 2**7 - 1


class int16(Integer):
    min = -(2**15)
    max = 2**15 - 1


class int24(Integer):
    min = -(2**23)
    max = 2**23 - 1


class int32(Integer):
    min = -(2**31)
    max = 2**31 - 1


class int40(Integer):
    min = -(2**39)
    max = 2**39 - 1


class int48(Integer):
    min = -(2**47)
    max = 2**47 - 1


class int56(Integer):
    min = -(2**55)
    max = 2**55 - 1


class int64(Integer):
    min = -(2**63)
    max = 2**63 - 1


class int72(Integer):
    min = -(2**71)
    max = 2**71 - 1


class int80(Integer):
    min = -(2**79)
    max = 2**79 - 1


class int88(Integer):
    min = -(2**87)
    max = 2**87 - 1


class int96(Integer):
    min = -(2**95)
    max = 2**95 - 1


class int104(Integer):
    min = -(2**103)
    max = 2**103 - 1


class int112(Integer):
    min = -(2**111)
    max = 2**111 - 1


class int120(Integer):
    min = -(2**119)
    max = 2**119 - 1


class int128(Integer):
    min = -(2**127)
    max = 2**127 - 1


class int136(Integer):
    min = -(2**135)
    max = 2**135 - 1


class int144(Integer):
    min = -(2**143)
    max = 2**143 - 1


class int152(Integer):
    min = -(2**151)
    max = 2**151 - 1


class int160(Integer):
    min = -(2**159)
    max = 2**159 - 1


class int168(Integer):
    min = -(2**167)
    max = 2**167 - 1


class int176(Integer):
    min = -(2**175)
    max = 2**175 - 1


class int184(Integer):
    min = -(2**183)
    max = 2**183 - 1


class int192(Integer):
    min = -(2**191)
    max = 2**191 - 1


class int200(Integer):
    min = -(2**199)
    max = 2**199 - 1


class int208(Integer):
    min = -(2**207)
    max = 2**207 - 1


class int216(Integer):
    min = -(2**215)
    max = 2**215 - 1


class int224(Integer):
    min = -(2**223)
    max = 2**223 - 1


class int232(Integer):
    min = -(2**231)
    max = 2**231 - 1


class int240(Integer):
    min = -(2**239)
    max = 2**239 - 1


class int248(Integer):
    min = -(2**247)
    max = 2**247 - 1


class int256(Integer):
    min = -(2**255)
    max = 2**255 - 1


class FixedSizeBytes(bytes, abc.ABC):
    length: int

    def __new__(cls, value):
        ret = super().__new__(cls, value)
        if len(ret) > cls.length:
            raise ValueError(f"Expected bytes of length {cls.length}, got {len(ret)}")
        elif len(ret) != cls.length:
            # extend
            return super().__new__(cls, ret + b"\x00" * (cls.length - len(ret)))
        return ret


class bytes1(FixedSizeBytes):
    length = 1


class bytes2(FixedSizeBytes):
    length = 2


class bytes3(FixedSizeBytes):
    length = 3


class bytes4(FixedSizeBytes):
    length = 4


class bytes5(FixedSizeBytes):
    length = 5


class bytes6(FixedSizeBytes):
    length = 6


class bytes7(FixedSizeBytes):
    length = 7


class bytes8(FixedSizeBytes):
    length = 8


class bytes9(FixedSizeBytes):
    length = 9


class bytes10(FixedSizeBytes):
    length = 10


class bytes11(FixedSizeBytes):
    length = 11


class bytes12(FixedSizeBytes):
    length = 12


class bytes13(FixedSizeBytes):
    length = 13


class bytes14(FixedSizeBytes):
    length = 14


class bytes15(FixedSizeBytes):
    length = 15


class bytes16(FixedSizeBytes):
    length = 16


class bytes17(FixedSizeBytes):
    length = 17


class bytes18(FixedSizeBytes):
    length = 18


class bytes19(FixedSizeBytes):
    length = 19


class bytes20(FixedSizeBytes):
    length = 20


class bytes21(FixedSizeBytes):
    length = 21


class bytes22(FixedSizeBytes):
    length = 22


class bytes23(FixedSizeBytes):
    length = 23


class bytes24(FixedSizeBytes):
    length = 24


class bytes25(FixedSizeBytes):
    length = 25


class bytes26(FixedSizeBytes):
    length = 26


class bytes27(FixedSizeBytes):
    length = 27


class bytes28(FixedSizeBytes):
    length = 28


class bytes29(FixedSizeBytes):
    length = 29


class bytes30(FixedSizeBytes):
    length = 30


class bytes31(FixedSizeBytes):
    length = 31


class bytes32(FixedSizeBytes):
    length = 32


T = TypeVar("T")


class FixedSizeList(List[T], abc.ABC):
    length: int

    def __init__(self, items: Iterable[T]):
        super().__init__(items)
        if len(self) != self.length:
            raise ValueError(f"Expected list of length {self.length}, got {len(self)}")


class List1(FixedSizeList[T]):
    length = 1


class List2(FixedSizeList[T]):
    length = 2


class List3(FixedSizeList[T]):
    length = 3


class List4(FixedSizeList[T]):
    length = 4


class List5(FixedSizeList[T]):
    length = 5


class List6(FixedSizeList[T]):
    length = 6


class List7(FixedSizeList[T]):
    length = 7


class List8(FixedSizeList[T]):
    length = 8


class List9(FixedSizeList[T]):
    length = 9


class List10(FixedSizeList[T]):
    length = 10


class List11(FixedSizeList[T]):
    length = 11


class List12(FixedSizeList[T]):
    length = 12


class List13(FixedSizeList[T]):
    length = 13


class List14(FixedSizeList[T]):
    length = 14


class List15(FixedSizeList[T]):
    length = 15


class List16(FixedSizeList[T]):
    length = 16


class List17(FixedSizeList[T]):
    length = 17


class List18(FixedSizeList[T]):
    length = 18


class List19(FixedSizeList[T]):
    length = 19


class List20(FixedSizeList[T]):
    length = 20


class List21(FixedSizeList[T]):
    length = 21


class List22(FixedSizeList[T]):
    length = 22


class List23(FixedSizeList[T]):
    length = 23


class List24(FixedSizeList[T]):
    length = 24


class List25(FixedSizeList[T]):
    length = 25


class List26(FixedSizeList[T]):
    length = 26


class List27(FixedSizeList[T]):
    length = 27


class List28(FixedSizeList[T]):
    length = 28


class List29(FixedSizeList[T]):
    length = 29


class List30(FixedSizeList[T]):
    length = 30


class List31(FixedSizeList[T]):
    length = 31


class List32(FixedSizeList[T]):
    length = 32
