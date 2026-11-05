from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from .core import Account


@dataclass
class UnknownEvent:
    origin: Account = field(init=False, compare=False, repr=False)
    topics: List[bytes]
    data: bytes


def read_from_memory(offset: int, length: int, memory: List) -> bytearray:
    def read_block(index: int) -> bytearray:
        word = memory[index]
        if word.startswith("0x"):
            word = word[2:]
        return bytearray.fromhex(word)

    start_block = offset // 32
    start_offset = offset % 32
    end_block = (offset + length) // 32
    end_offset = (offset + length) % 32

    if start_block == end_block:
        if start_block >= len(memory):
            return bytearray(length)
        return read_block(start_block)[start_offset:end_offset]
    else:
        if start_block >= len(memory):
            ret = bytearray(32 - start_offset)
        else:
            ret = read_block(start_block)[start_offset:]
        for i in range(start_block + 1, end_block):
            if i >= len(memory):
                ret += bytearray(32)
            else:
                ret += read_block(i)
        if end_block >= len(memory):
            ret += bytearray(end_offset)
        else:
            ret += read_block(end_block)[:end_offset]
        return ret
