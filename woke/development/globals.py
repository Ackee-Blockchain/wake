from __future__ import annotations

from pathlib import Path
from types import TracebackType
from typing import Callable, Optional, TYPE_CHECKING

from pdbr import RichPdb

from woke.config import WokeConfig
from woke.utils.file_utils import is_relative_to

if TYPE_CHECKING:
    from woke.testing.coverage import CoverageHandler


# must be declared before functions that use it because of a bug in Python (https://bugs.python.org/issue34939)
_exception_handler: Optional[Callable[[Exception], None]] = None
_exception_handled = False

_coverage_handler: Optional[CoverageHandler] = None

_config: Optional[WokeConfig] = None


def attach_debugger(e: Exception):
    global _exception_handled

    if _exception_handled:
        return
    _exception_handled = True

    import sys
    import traceback

    from woke.cli.console import console

    tb: Optional[TracebackType] = sys.exc_info()[2]
    assert tb is not None
    console.print_exception()

    frames = []

    for frame, lineno in traceback.walk_tb(tb):
        frames.append((frame, lineno))

    frames_up = 0
    for frame, lineno in reversed(frames):
        if is_relative_to(
            Path(frame.f_code.co_filename), Path.cwd()
        ) and not is_relative_to(
            Path(frame.f_code.co_filename), Path().cwd() / "pytypes"
        ):
            break
        frames_up += 1

    p = RichPdb()
    p.rcLines.extend(["up %d" % frames_up] if frames_up > 0 else [])
    p.reset()
    p.interaction(None, tb)


def get_exception_handler() -> Optional[Callable[[Exception], None]]:
    return _exception_handler


def set_exception_handler(handler: Callable[[Exception], None]):
    global _exception_handler
    _exception_handler = handler


def reset_exception_handled():
    global _exception_handled
    _exception_handled = False


def get_config() -> WokeConfig:
    global _config
    if _config is None:
        _config = WokeConfig()
        _config.load_configs()
    return _config


def set_config(config: WokeConfig):
    global _config
    _config = config


def set_coverage_handler(coverage_handler: CoverageHandler):
    global _coverage_handler
    _coverage_handler = coverage_handler


def get_coverage_handler() -> Optional[CoverageHandler]:
    return _coverage_handler
