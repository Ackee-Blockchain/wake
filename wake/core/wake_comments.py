from dataclasses import dataclass
from typing import Dict, List, Optional

from wake.utils.keyed_default_dict import KeyedDefaultDict


@dataclass
class WakeComment:
    codes: Optional[List[str]]
    start_line: int
    end_line: int


def error_commented_out(
    error_code: str,
    start_line: int,
    end_line: int,
    wake_comments: Dict[str, Dict[int, WakeComment]],
) -> bool:
    comments = KeyedDefaultDict(
        lambda t: wake_comments.get(t, {})  # pyright: ignore reportGeneralTypeIssues
    )

    for l in range(start_line, end_line + 1):
        if l in comments["wake-disable-line"]:
            comment: WakeComment = comments["wake-disable-line"][l]
            if comment.codes is None or error_code in comment.codes:
                return True

    for l in range(start_line - 1, end_line):
        if l in comments["wake-disable-next-line"]:
            comment: WakeComment = comments["wake-disable-next-line"][l]
            if comment.codes is None or error_code in comment.codes:
                return True

    enable_keys: List[int] = sorted(comments["wake-enable"].keys())
    disable_keys: List[int] = sorted(comments["wake-disable"].keys())

    disabled_line = None
    for k in disable_keys:
        if k >= start_line:
            break

        comment: WakeComment = comments["wake-disable"][k]
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
            comments["wake-enable"][k].codes is None
            or error_code in comments["wake-enable"][k].codes
        ):
            return False

    return True
