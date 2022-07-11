from woke.lsp.common_structures import Position, Range


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
