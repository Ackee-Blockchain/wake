from __future__ import annotations

import inspect
import math
from functools import wraps
from typing import TYPE_CHECKING, Callable, Iterable, List, Tuple, TypeVar

from Crypto.Hash import keccak

if TYPE_CHECKING:
    from woke.testing.core import ChainInterface


def snapshot_and_revert(devchain_interface: ChainInterface):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            with devchain_interface.snapshot_and_revert():
                return fn(*args, **kwargs)

        return wrapper

    return decorator


def connect(devchain_interface: ChainInterface, uri: str):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            with devchain_interface.connect(uri):
                return fn(*args, **kwargs)

        return wrapper

    return decorator


def change_automine(devchain_interface: ChainInterface, automine: bool):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            with devchain_interface.change_automine(automine):
                return fn(*args, **kwargs)

        return wrapper

    return decorator


def format_int(x: int) -> str:
    if abs(x) < 10**5:
        return f"{x:_}"
    no_of_digits = int(math.log10(abs(x))) + 1
    if x % 10 ** (no_of_digits - 3) == 0:
        return f"{x:.2e}"
    return f"{x:.2E} ({x:_})"


def exists(a) -> bool:
    if a is None:
        return False
    if len(a) >= 0:
        return True
    return bool(a)


T = TypeVar("T")


def partition(
    seq: Iterable[T], predicate: Callable[[T], bool]
) -> Tuple[List[T], List[T]]:
    p = []
    not_p = []
    for el in seq:
        if predicate(el):
            p.append(el)
        else:
            not_p.append(el)
    return p, not_p


def keccak256(b: bytes) -> bytes:
    h = keccak.new(data=b, digest_bits=256)
    return h.digest()


def get_current_fn_name(back_count=1) -> str:
    frame = inspect.currentframe()
    assert frame is not None
    for _ in range(back_count):
        frame = frame.f_back
        assert frame is not None
    return frame.f_code.co_name


def negate(fn):
    def inner(*args, **kwargs) -> bool:
        return not fn(*args, **kwargs)

    return inner


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
