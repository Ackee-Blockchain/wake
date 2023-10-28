from typing import Set

from intervaltree import Interval

from wake.lsp.common_structures import Position, Range


def changes_to_byte_offset(changes: Set[Interval]) -> int:
    byte_offset = 0
    tag: str
    j1: int
    j2: int
    for change in changes:
        tag, j1, j2 = change.data
        if tag == "insert":
            byte_offset += j2 - j1 - 1
        elif tag == "delete":
            byte_offset -= change.end - change.begin - 1
        elif tag == "replace":
            byte_offset += j2 - j1 - (change.end - change.begin)
        else:
            raise ValueError(f"Unknown tag {tag}")
    return byte_offset


def position_within_range(pos: Position, range: Range) -> bool:
    if pos.line < range.start.line:
        return False
    if pos.line == range.start.line and pos.character < range.start.character:
        return False
    if pos.line > range.end.line:
        return False
    if pos.line == range.end.line and pos.character > range.end.character:
        return False
    return True
