from contextlib import contextmanager
from os import chdir
from pathlib import Path
from typing import Set, Union


@contextmanager
def change_cwd(path: Union[str, Path]):
    """
    Temporary change the current working directory to the path provided as the first argument.
    """
    orig_cwd = Path.cwd().resolve()
    try:
        chdir(Path(path).resolve())
        yield
    finally:
        chdir(orig_cwd)


@contextmanager
def recursion_guard(guard: Set, *args):
    try:
        guard.add(args)
        yield
    finally:
        guard.remove(args)
