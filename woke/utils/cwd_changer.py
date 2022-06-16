from typing import Union
from contextlib import contextmanager
from pathlib import Path
from os import chdir


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
