import pytest

from wake.development.internal import read_from_memory


@pytest.mark.parametrize("word_format", ["plain", "prefixed", "mixed"])
@pytest.mark.parametrize(
    "offset,length",
    [
        (0, 0),
        (17, 0),
        (96, 0),
        (0, 1),
        (5, 11),
        (31, 2),
        (0, 32),
        (32, 32),
        (5, 75),
        (31, 66),
        (90, 20),
        (96, 12),
        (128, 7),
    ],
)
def test_read_from_memory(word_format, offset, length):
    data = bytes(range(96))
    memory = [data[i : i + 32].hex() for i in range(0, len(data), 32)]
    memory = [
        "0x" + word
        if word_format == "prefixed" or (word_format == "mixed" and i % 2 == 0)
        else word
        for i, word in enumerate(memory)
    ]
    original_memory = memory.copy()

    result = read_from_memory(offset, length, memory)

    assert isinstance(result, bytearray)
    assert result == data[offset : offset + length].ljust(length, b"\x00")
    assert memory == original_memory


@pytest.mark.parametrize("offset,length", [(0, 0), (0, 20), (20, 40)])
def test_read_from_empty_memory(offset, length):
    assert read_from_memory(offset, length, []) == bytearray(length)
