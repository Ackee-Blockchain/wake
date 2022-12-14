from dataclasses import dataclass
from enum import IntEnum
from typing import List


@dataclass
class UnknownEvent:
    topics: List[bytes]
    data: bytes


class TransactionRevertedError(Exception):
    pass


@dataclass
class UnknownTransactionRevertedError(TransactionRevertedError):
    data: bytes


@dataclass
class Error(TransactionRevertedError):
    _abi = {
        "name": "Error",
        "type": "error",
        "inputs": [{"name": "message", "type": "string"}],
    }
    message: str


class PanicCodeEnum(IntEnum):
    GENERIC = 0
    "Generic compiler panic"
    ASSERT_FAIL = 1
    "Assert evaluated to false"
    UNDERFLOW_OVERFLOW = 0x11
    "Integer underflow or overflow"
    DIVISION_MODULO_BY_ZERO = 0x12
    "Division or modulo by zero"
    INVALID_CONVERSION_TO_ENUM = 0x21
    "Too big or negative integer for conversion to enum"
    ACCESS_TO_INCORRECTLY_ENCODED_STORAGE_BYTE_ARRAY = 0x22
    "Access to incorrectly encoded storage byte array"
    POP_EMPTY_ARRAY = 0x31
    ".pop() on empty array"
    INDEX_ACCESS_OUT_OF_BOUNDS = 0x32
    "Out-of-bounds or negative index access to fixed-length array"
    TOO_MUCH_MEMORY_ALLOCATED = 0x41
    "Too much memory allocated"
    INVALID_INTERNAL_FUNCTION_CALL = 0x51
    "Called invalid internal function"


@dataclass
class Panic(TransactionRevertedError):
    _abi = {
        "name": "Panic",
        "type": "error",
        "inputs": [{"name": "code", "type": "uint256"}],
    }
    code: "PanicCodeEnum"
