from dataclasses import dataclass
from typing import Dict, List, Optional

from woke.utils.keyed_default_dict import KeyedDefaultDict


@dataclass
class WokeComment:
    codes: Optional[List[str]]
    start_line: int
    end_line: int


def error_commented_out(
    error_code: str,
    start_line: int,
    end_line: int,
    woke_comments: Dict[str, Dict[int, WokeComment]],
) -> bool:
    comments = KeyedDefaultDict(
        lambda t: woke_comments.get(t, {})  # pyright: ignore reportGeneralTypeIssues
    )

    for l in range(start_line, end_line + 1):
        if l in comments["woke-disable-line"]:
            comment: WokeComment = comments["woke-disable-line"][l]
            if comment.codes is None or error_code in comment.codes:
                return True

    for l in range(start_line - 1, end_line):
        if l in comments["woke-disable-next-line"]:
            comment: WokeComment = comments["woke-disable-next-line"][l]
            if comment.codes is None or error_code in comment.codes:
                return True

    enable_keys: List[int] = sorted(comments["woke-enable"].keys())
    disable_keys: List[int] = sorted(comments["woke-disable"].keys())

    disabled_line = None
    for k in disable_keys:
        if k >= start_line:
            break

        comment: WokeComment = comments["woke-disable"][k]
        if comment.codes is None or error_code in comment.codes:
            disabled_line = k

    if disabled_line is None:
        return False

    for k in enable_keys:
        if k <= disabled_line:
            continue
        if k >= start_line:
            break

        if (
            comments["woke-enable"][k].codes is None
            or error_code in comments["woke-enable"][k].codes
        ):
            return False

    return True
