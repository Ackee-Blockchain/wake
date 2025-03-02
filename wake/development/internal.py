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


class ExternalEvent:
    _event_name: str
    _event_full_name: str
    origin: Account

    def __init__(self, _event_full_name, **kwargs):
        self._event_full_name = _event_full_name

        if "." in self._event_full_name:
            self._event_name = self._event_full_name.split(".")[-1]
        else:
            self._event_name = self._event_full_name

        self.origin = None

        self._extra_attrs = {}
        for key, value in kwargs.items():
            setattr(self, key, value)
            self._extra_attrs[key] = value

    def __repr__(self):
        cls_name = self.__class__.__name__
        base_repr = f"{cls_name}(_event_full_name='{self._event_full_name}'"

        for key, value in self._extra_attrs.items():
            if isinstance(value, str):
                base_repr += f", {key}='{value}'"
            else:
                base_repr += f", {key}={value}"

        base_repr += ")"
        return base_repr

    def __str__(self):
        return self.__repr__()

    def __eq__(self, other):
        if not isinstance(other, ExternalEvent):
            return False

        if self._event_full_name != other._event_full_name:
            return False

        for key, value in self._extra_attrs.items():
            if not hasattr(other, key) or getattr(other, key) != value:
                return False

        for key in getattr(other, "_extra_attrs", {}):
            if key not in self._extra_attrs:
                return False

        return True

    def __hash__(self):
        # Create a tuple of (_event_full_name, (key1, value1), (key2, value2), ...)
        # and hash that tuple
        try:
            items = [(key, value) for key, value in sorted(self._extra_attrs.items())]
            return hash((self._event_full_name, tuple(items)))
        except TypeError as e:
            # Provide a more informative error message
            for key, value in self._extra_attrs.items():
                try:
                    hash(value)
                except TypeError:
                    raise TypeError(
                        f"ExternalEvent unhashable: attribute '{key}' with value {value!r} is not hashable"
                    ) from e
            # If we couldn't identify the specific unhashable attribute
            raise


def read_from_memory(offset: int, length: int, memory: List) -> bytes:
    if isinstance(memory, str):
        m = bytes.fromhex(memory[2:] if memory.startswith("0x") else memory)
        return m[offset : offset + length]

    start_block = offset // 32
    start_offset = offset % 32
    end_block = (offset + length) // 32
    end_offset = (offset + length) % 32

    if start_block == end_block:
        if start_block >= len(memory):
            return bytes(length)
        return bytes.fromhex(memory[start_block])[start_offset:end_offset]
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
        return bytes(ret)
