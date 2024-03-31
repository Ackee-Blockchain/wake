import abc
from typing import TYPE_CHECKING, Iterable, List, TypeVar

NoneType = type(None)


if TYPE_CHECKING:
    uint8 = int
    uint16 = int
    uint24 = int
    uint32 = int
    uint40 = int
    uint48 = int
    uint56 = int
    uint64 = int
    uint72 = int
    uint80 = int
    uint88 = int
    uint96 = int
    uint104 = int
    uint112 = int
    uint120 = int
    uint128 = int
    uint136 = int
    uint144 = int
    uint152 = int
    uint160 = int
    uint168 = int
    uint176 = int
    uint184 = int
    uint192 = int
    uint200 = int
    uint208 = int
    uint216 = int
    uint224 = int
    uint232 = int
    uint240 = int
    uint248 = int
    uint256 = int
    uint = uint256

    int8 = int
    int16 = int
    int24 = int
    int32 = int
    int40 = int
    int48 = int
    int56 = int
    int64 = int
    int72 = int
    int80 = int
    int88 = int
    int96 = int
    int104 = int
    int112 = int
    int120 = int
    int128 = int
    int136 = int
    int144 = int
    int152 = int
    int160 = int
    int168 = int
    int176 = int
    int184 = int
    int192 = int
    int200 = int
    int208 = int
    int216 = int
    int224 = int
    int232 = int
    int240 = int
    int248 = int
    int256 = int

    bytes1 = bytes
    bytes2 = bytes
    bytes3 = bytes
    bytes4 = bytes
    bytes5 = bytes
    bytes6 = bytes
    bytes7 = bytes
    bytes8 = bytes
    bytes9 = bytes
    bytes10 = bytes
    bytes11 = bytes
    bytes12 = bytes
    bytes13 = bytes
    bytes14 = bytes
    bytes15 = bytes
    bytes16 = bytes
    bytes17 = bytes
    bytes18 = bytes
    bytes19 = bytes
    bytes20 = bytes
    bytes21 = bytes
    bytes22 = bytes
    bytes23 = bytes
    bytes24 = bytes
    bytes25 = bytes
    bytes26 = bytes
    bytes27 = bytes
    bytes28 = bytes
    bytes29 = bytes
    bytes30 = bytes
    bytes31 = bytes
    bytes32 = bytes

    T = TypeVar("T")

    List1 = List[T]
    List2 = List[T]
    List3 = List[T]
    List4 = List[T]
    List5 = List[T]
    List6 = List[T]
    List7 = List[T]
    List8 = List[T]
    List9 = List[T]
    List10 = List[T]
    List11 = List[T]
    List12 = List[T]
    List13 = List[T]
    List14 = List[T]
    List15 = List[T]
    List16 = List[T]
    List17 = List[T]
    List18 = List[T]
    List19 = List[T]
    List20 = List[T]
    List21 = List[T]
    List22 = List[T]
    List23 = List[T]
    List24 = List[T]
    List25 = List[T]
    List26 = List[T]
    List27 = List[T]
    List28 = List[T]
    List29 = List[T]
    List30 = List[T]
    List31 = List[T]
    List32 = List[T]

else:

    class Integer(int, abc.ABC):
        def __new__(cls, value):
            ret = super().__new__(cls, value)
            if not hasattr(cls, "min") or not hasattr(cls, "max"):
                return ret
            if ret < cls.min or ret > cls.max:
                raise ValueError(
                    f"Expected value within range [{cls.min}, {cls.max}], got {ret}"
                )
            return ret

    class uint8(Integer):
        pass

    uint8.min = uint8(0)
    uint8.max = uint8(2**8 - 1)

    class uint16(Integer):
        pass

    uint16.min = uint16(0)
    uint16.max = uint16(2**16 - 1)

    class uint24(Integer):
        pass

    uint24.min = uint24(0)
    uint24.max = uint24(2**24 - 1)

    class uint32(Integer):
        pass

    uint32.min = uint32(0)
    uint32.max = uint32(2**32 - 1)

    class uint40(Integer):
        pass

    uint40.min = uint40(0)
    uint40.max = uint40(2**40 - 1)

    class uint48(Integer):
        pass

    uint48.min = uint48(0)
    uint48.max = uint48(2**48 - 1)

    class uint56(Integer):
        pass

    uint56.min = uint56(0)
    uint56.max = uint56(2**56 - 1)

    class uint64(Integer):
        pass

    uint64.min = uint64(0)
    uint64.max = uint64(2**64 - 1)

    class uint72(Integer):
        pass

    uint72.min = uint72(0)
    uint72.max = uint72(2**72 - 1)

    class uint80(Integer):
        pass

    uint80.min = uint80(0)
    uint80.max = uint80(2**80 - 1)

    class uint88(Integer):
        pass

    uint88.min = uint88(0)
    uint88.max = uint88(2**88 - 1)

    class uint96(Integer):
        pass

    uint96.min = uint96(0)
    uint96.max = uint96(2**96 - 1)

    class uint104(Integer):
        pass

    uint104.min = uint104(0)
    uint104.max = uint104(2**104 - 1)

    class uint112(Integer):
        pass

    uint112.min = uint112(0)
    uint112.max = uint112(2**112 - 1)

    class uint120(Integer):
        pass

    uint120.min = uint120(0)
    uint120.max = uint120(2**120 - 1)

    class uint128(Integer):
        pass

    uint128.min = uint128(0)
    uint128.max = uint128(2**128 - 1)

    class uint136(Integer):
        pass

    uint136.min = uint136(0)
    uint136.max = uint136(2**136 - 1)

    class uint144(Integer):
        pass

    uint144.min = uint144(0)
    uint144.max = uint144(2**144 - 1)

    class uint152(Integer):
        pass

    uint152.min = uint152(0)
    uint152.max = uint152(2**152 - 1)

    class uint160(Integer):
        pass

    uint160.min = uint160(0)
    uint160.max = uint160(2**160 - 1)

    class uint168(Integer):
        pass

    uint168.min = uint168(0)
    uint168.max = uint168(2**168 - 1)

    class uint176(Integer):
        pass

    uint176.min = uint176(0)
    uint176.max = uint176(2**176 - 1)

    class uint184(Integer):
        pass

    uint184.min = uint184(0)
    uint184.max = uint184(2**184 - 1)

    class uint192(Integer):
        pass

    uint192.min = uint192(0)
    uint192.max = uint192(2**192 - 1)

    class uint200(Integer):
        pass

    uint200.min = uint200(0)
    uint200.max = uint200(2**200 - 1)

    class uint208(Integer):
        pass

    uint208.min = uint208(0)
    uint208.max = uint208(2**208 - 1)

    class uint216(Integer):
        pass

    uint216.min = uint216(0)
    uint216.max = uint216(2**216 - 1)

    class uint224(Integer):
        pass

    uint224.min = uint224(0)
    uint224.max = uint224(2**224 - 1)

    class uint232(Integer):
        pass

    uint232.min = uint232(0)
    uint232.max = uint232(2**232 - 1)

    class uint240(Integer):
        pass

    uint240.min = uint240(0)
    uint240.max = uint240(2**240 - 1)

    class uint248(Integer):
        pass

    uint248.min = uint248(0)
    uint248.max = uint248(2**248 - 1)

    class uint256(Integer):
        pass

    uint256.min = uint256(0)
    uint256.max = uint256(2**256 - 1)

    uint = uint256

    uint_map = {
        8: uint8,
        16: uint16,
        24: uint24,
        32: uint32,
        40: uint40,
        48: uint48,
        56: uint56,
        64: uint64,
        72: uint72,
        80: uint80,
        88: uint88,
        96: uint96,
        104: uint104,
        112: uint112,
        120: uint120,
        128: uint128,
        136: uint136,
        144: uint144,
        152: uint152,
        160: uint160,
        168: uint168,
        176: uint176,
        184: uint184,
        192: uint192,
        200: uint200,
        208: uint208,
        216: uint216,
        224: uint224,
        232: uint232,
        240: uint240,
        248: uint248,
        256: uint256,
    }

    class int8(Integer):
        pass

    int8.min = int8(-(2**7))
    int8.max = int8(2**7 - 1)

    class int16(Integer):
        pass

    int16.min = int16(-(2**15))
    int16.max = int16(2**15 - 1)

    class int24(Integer):
        pass

    int24.min = int24(-(2**23))
    int24.max = int24(2**23 - 1)

    class int32(Integer):
        pass

    int32.min = int32(-(2**31))
    int32.max = int32(2**31 - 1)

    class int40(Integer):
        pass

    int40.min = int40(-(2**39))
    int40.max = int40(2**39 - 1)

    class int48(Integer):
        pass

    int48.min = int48(-(2**47))
    int48.max = int48(2**47 - 1)

    class int56(Integer):
        pass

    int56.min = int56(-(2**55))
    int56.max = int56(2**55 - 1)

    class int64(Integer):
        pass

    int64.min = int64(-(2**63))
    int64.max = int64(2**63 - 1)

    class int72(Integer):
        pass

    int72.min = int72(-(2**71))
    int72.max = int72(2**71 - 1)

    class int80(Integer):
        pass

    int80.min = int80(-(2**79))
    int80.max = int80(2**79 - 1)

    class int88(Integer):
        pass

    int88.min = int88(-(2**87))
    int88.max = int88(2**87 - 1)

    class int96(Integer):
        pass

    int96.min = int96(-(2**95))
    int96.max = int96(2**95 - 1)

    class int104(Integer):
        pass

    int104.min = int104(-(2**103))
    int104.max = int104(2**103 - 1)

    class int112(Integer):
        pass

    int112.min = int112(-(2**111))
    int112.max = int112(2**111 - 1)

    class int120(Integer):
        pass

    int120.min = int120(-(2**119))
    int120.max = int120(2**119 - 1)

    class int128(Integer):
        pass

    int128.min = int128(-(2**127))
    int128.max = int128(2**127 - 1)

    class int136(Integer):
        pass

    int136.min = int136(-(2**135))
    int136.max = int136(2**135 - 1)

    class int144(Integer):
        pass

    int144.min = int144(-(2**143))
    int144.max = int144(2**143 - 1)

    class int152(Integer):
        pass

    int152.min = int152(-(2**151))
    int152.max = int152(2**151 - 1)

    class int160(Integer):
        pass

    int160.min = int160(-(2**159))
    int160.max = int160(2**159 - 1)

    class int168(Integer):
        pass

    int168.min = int168(-(2**167))
    int168.max = int168(2**167 - 1)

    class int176(Integer):
        pass

    int176.min = int176(-(2**175))
    int176.max = int176(2**175 - 1)

    class int184(Integer):
        pass

    int184.min = int184(-(2**183))
    int184.max = int184(2**183 - 1)

    class int192(Integer):
        pass

    int192.min = int192(-(2**191))
    int192.max = int192(2**191 - 1)

    class int200(Integer):
        pass

    int200.min = int200(-(2**199))
    int200.max = int200(2**199 - 1)

    class int208(Integer):
        pass

    int208.min = int208(-(2**207))
    int208.max = int208(2**207 - 1)

    class int216(Integer):
        pass

    int216.min = int216(-(2**215))
    int216.max = int216(2**215 - 1)

    class int224(Integer):
        pass

    int224.min = int224(-(2**223))
    int224.max = int224(2**223 - 1)

    class int232(Integer):
        pass

    int232.min = int232(-(2**231))
    int232.max = int232(2**231 - 1)

    class int240(Integer):
        pass

    int240.min = int240(-(2**239))
    int240.max = int240(2**239 - 1)

    class int248(Integer):
        pass

    int248.min = int248(-(2**247))
    int248.max = int248(2**247 - 1)

    class int256(Integer):
        pass

    int256.min = int256(-(2**255))
    int256.max = int256(2**255 - 1)

    int_map = {
        8: int8,
        16: int16,
        24: int24,
        32: int32,
        40: int40,
        48: int48,
        56: int56,
        64: int64,
        72: int72,
        80: int80,
        88: int88,
        96: int96,
        104: int104,
        112: int112,
        120: int120,
        128: int128,
        136: int136,
        144: int144,
        152: int152,
        160: int160,
        168: int168,
        176: int176,
        184: int184,
        192: int192,
        200: int200,
        208: int208,
        216: int216,
        224: int224,
        232: int232,
        240: int240,
        248: int248,
        256: int256,
    }

    class FixedSizeBytes(bytes, abc.ABC):
        length: uint8

        def __new__(cls, value):
            ret = super().__new__(cls, value)
            if len(ret) > cls.length:
                raise ValueError(
                    f"Expected bytes of length {cls.length}, got {len(ret)}"
                )
            elif len(ret) != cls.length:
                # extend
                return super().__new__(cls, ret + b"\x00" * (cls.length - len(ret)))
            return ret

    class bytes1(FixedSizeBytes):
        length = uint8(1)

    class bytes2(FixedSizeBytes):
        length = uint8(2)

    class bytes3(FixedSizeBytes):
        length = uint8(3)

    class bytes4(FixedSizeBytes):
        length = uint8(4)

    class bytes5(FixedSizeBytes):
        length = uint8(5)

    class bytes6(FixedSizeBytes):
        length = uint8(6)

    class bytes7(FixedSizeBytes):
        length = uint8(7)

    class bytes8(FixedSizeBytes):
        length = uint8(8)

    class bytes9(FixedSizeBytes):
        length = uint8(9)

    class bytes10(FixedSizeBytes):
        length = uint8(10)

    class bytes11(FixedSizeBytes):
        length = uint8(11)

    class bytes12(FixedSizeBytes):
        length = uint8(12)

    class bytes13(FixedSizeBytes):
        length = uint8(13)

    class bytes14(FixedSizeBytes):
        length = uint8(14)

    class bytes15(FixedSizeBytes):
        length = uint8(15)

    class bytes16(FixedSizeBytes):
        length = uint8(16)

    class bytes17(FixedSizeBytes):
        length = uint8(17)

    class bytes18(FixedSizeBytes):
        length = uint8(18)

    class bytes19(FixedSizeBytes):
        length = uint8(19)

    class bytes20(FixedSizeBytes):
        length = uint8(20)

    class bytes21(FixedSizeBytes):
        length = uint8(21)

    class bytes22(FixedSizeBytes):
        length = uint8(22)

    class bytes23(FixedSizeBytes):
        length = uint8(23)

    class bytes24(FixedSizeBytes):
        length = uint8(24)

    class bytes25(FixedSizeBytes):
        length = uint8(25)

    class bytes26(FixedSizeBytes):
        length = uint8(26)

    class bytes27(FixedSizeBytes):
        length = uint8(27)

    class bytes28(FixedSizeBytes):
        length = uint8(28)

    class bytes29(FixedSizeBytes):
        length = uint8(29)

    class bytes30(FixedSizeBytes):
        length = uint8(30)

    class bytes31(FixedSizeBytes):
        length = uint8(31)

    class bytes32(FixedSizeBytes):
        length = uint8(32)

    fixed_bytes_map = {
        1: bytes1,
        2: bytes2,
        3: bytes3,
        4: bytes4,
        5: bytes5,
        6: bytes6,
        7: bytes7,
        8: bytes8,
        9: bytes9,
        10: bytes10,
        11: bytes11,
        12: bytes12,
        13: bytes13,
        14: bytes14,
        15: bytes15,
        16: bytes16,
        17: bytes17,
        18: bytes18,
        19: bytes19,
        20: bytes20,
        21: bytes21,
        22: bytes22,
        23: bytes23,
        24: bytes24,
        25: bytes25,
        26: bytes26,
        27: bytes27,
        28: bytes28,
        29: bytes29,
        30: bytes30,
        31: bytes31,
        32: bytes32,
    }

    T = TypeVar("T")

    class FixedSizeList(List[T], abc.ABC):
        length: uint256

        def __init__(self, items: Iterable[T]):
            super().__init__(items)
            if len(self) != self.length:
                raise ValueError(
                    f"Expected list of length {self.length}, got {len(self)}"
                )

    class List1(FixedSizeList[T]):
        length = uint256(1)

    class List2(FixedSizeList[T]):
        length = uint256(2)

    class List3(FixedSizeList[T]):
        length = uint256(3)

    class List4(FixedSizeList[T]):
        length = uint256(4)

    class List5(FixedSizeList[T]):
        length = uint256(5)

    class List6(FixedSizeList[T]):
        length = uint256(6)

    class List7(FixedSizeList[T]):
        length = uint256(7)

    class List8(FixedSizeList[T]):
        length = uint256(8)

    class List9(FixedSizeList[T]):
        length = uint256(9)

    class List10(FixedSizeList[T]):
        length = uint256(10)

    class List11(FixedSizeList[T]):
        length = uint256(11)

    class List12(FixedSizeList[T]):
        length = uint256(12)

    class List13(FixedSizeList[T]):
        length = uint256(13)

    class List14(FixedSizeList[T]):
        length = uint256(14)

    class List15(FixedSizeList[T]):
        length = uint256(15)

    class List16(FixedSizeList[T]):
        length = uint256(16)

    class List17(FixedSizeList[T]):
        length = uint256(17)

    class List18(FixedSizeList[T]):
        length = uint256(18)

    class List19(FixedSizeList[T]):
        length = uint256(19)

    class List20(FixedSizeList[T]):
        length = uint256(20)

    class List21(FixedSizeList[T]):
        length = uint256(21)

    class List22(FixedSizeList[T]):
        length = uint256(22)

    class List23(FixedSizeList[T]):
        length = uint256(23)

    class List24(FixedSizeList[T]):
        length = uint256(24)

    class List25(FixedSizeList[T]):
        length = uint256(25)

    class List26(FixedSizeList[T]):
        length = uint256(26)

    class List27(FixedSizeList[T]):
        length = uint256(27)

    class List28(FixedSizeList[T]):
        length = uint256(28)

    class List29(FixedSizeList[T]):
        length = uint256(29)

    class List30(FixedSizeList[T]):
        length = uint256(30)

    class List31(FixedSizeList[T]):
        length = uint256(31)

    class List32(FixedSizeList[T]):
        length = uint256(32)

    fixed_list_map = {
        1: List1,
        2: List2,
        3: List3,
        4: List4,
        5: List5,
        6: List6,
        7: List7,
        8: List8,
        9: List9,
        10: List10,
        11: List11,
        12: List12,
        13: List13,
        14: List14,
        15: List15,
        16: List16,
        17: List17,
        18: List18,
        19: List19,
        20: List20,
        21: List21,
        22: List22,
        23: List23,
        24: List24,
        25: List25,
        26: List26,
        27: List27,
        28: List28,
        29: List29,
        30: List30,
        31: List31,
        32: List32,
    }
