import inspect
from contextlib import contextmanager
from dataclasses import dataclass, fields
from enum import IntEnum
from typing import Any, List, Optional


@dataclass
class UnknownEvent:
    topics: List[bytes]
    data: bytes


@dataclass
class TransactionRevertedError(Exception):
    def __str__(self):
        s = ", ".join([f"{f.name}={getattr(self, f.name)!r}" for f in fields(self)])
        return f"{self.__class__.__qualname__}({s})"


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


class ExceptionWrapper:
    value: Optional[Exception] = None


@contextmanager
def must_revert(exceptions=TransactionRevertedError):
    if isinstance(exceptions, (tuple, list)):
        types = tuple(
            type(x) if not inspect.isclass(x) else x for x in exceptions
        )  # pyright: reportGeneralTypeIssues=false
    else:
        types = type(exceptions) if not inspect.isclass(exceptions) else exceptions

    wrapper = ExceptionWrapper()

    try:
        yield wrapper
        raise AssertionError(f"Expected revert of type {exceptions}")
    except types as e:  # pyright: reportGeneralTypeIssues=false
        wrapper.value = e

        if isinstance(exceptions, (tuple, list)):
            for ex, t in zip(
                exceptions, types
            ):  # pyright: reportGeneralTypeIssues=false
                if isinstance(ex, t) and not inspect.isclass(ex):
                    assert e == ex, f"Expected {ex} but got {e}"
                    return
        else:
            if not inspect.isclass(exceptions):
                assert e == exceptions, f"Expected {e} but got {exceptions}"


@contextmanager
def may_revert(exceptions=TransactionRevertedError):
    if isinstance(exceptions, (tuple, list)):
        types = tuple(type(x) if not inspect.isclass(x) else x for x in exceptions)
    else:
        types = type(exceptions) if not inspect.isclass(exceptions) else exceptions

    wrapper = ExceptionWrapper()

    try:
        yield wrapper
    except types as e:
        wrapper.value = e

        if isinstance(exceptions, (tuple, list)):
            for ex, t in zip(exceptions, types):
                if isinstance(ex, t) and not inspect.isclass(ex):
                    assert e == ex, f"Expected {ex} but got {e}"
                    return
        else:
            if not inspect.isclass(exceptions):
                assert e == exceptions, f"Expected {e} but got {exceptions}"


def read_from_memory(offset: int, length: int, memory: List) -> bytearray:
    start_block = offset // 32
    start_offset = offset % 32
    end_block = (offset + length) // 32
    end_offset = (offset + length) % 32

    if start_block == end_block:
        if start_block >= len(memory):
            return bytearray(length)
        return bytearray.fromhex(memory[start_block])[start_offset:end_offset]
    else:
        if start_block >= len(memory):
            ret = bytearray(32 - start_offset)
        else:
            ret = bytearray.fromhex(memory[start_block])[start_offset:]
        for i in range(start_block + 1, end_block):
            if i >= len(memory):
                ret += bytearray(32)
            else:
                ret += bytearray.fromhex(memory[i])
        if end_block >= len(memory):
            ret += bytearray(end_offset)
        else:
            ret += bytearray.fromhex(memory[end_block])[:end_offset]
        return ret
