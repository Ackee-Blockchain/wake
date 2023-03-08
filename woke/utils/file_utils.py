from __future__ import annotations

import pathlib
import shutil
from os import PathLike
from typing import Union


def is_relative_to(path: pathlib.PurePath, *other: Union[str, PathLike[str]]):
    """
    Return True if the path is relative to another path or False.
    Backported from Python 3.9 (https://github.com/python/cpython/blob/75a6441718dcbc65d993c9544e67e25bef120e82/Lib/pathlib.py#L687-L694)
    """
    try:
        path.relative_to(*other)
        return True
    except ValueError:
        return False


def copy_dir(
    src_dir: pathlib.Path,
    dst_dir: pathlib.Path,
    *,
    overwrite: bool = False,
    raise_on_existing: bool = False,
) -> None:
    """
    Copy contents of src_dir and create dst_dir if it doesn't exist.
    Overwrite files if overwrite is True. Raise FileExistsError if raise_on_existing is True and
    existing files are found.
    """
    dst_dir.mkdir(exist_ok=True)
    src_dst_paths = [
        (p.absolute(), dst_dir / p.relative_to(src_dir)) for p in src_dir.rglob("*")
    ]
    if not overwrite and raise_on_existing:
        existing_files = []
        for _, dst_path in src_dst_paths:
            if dst_path.exists():
                existing_files.append(str(dst_path))
        if existing_files:
            raise FileExistsError(f"Existing files: {existing_files}")

    for src_path, dst_path in src_dst_paths:
        if src_path.is_dir():
            dst_path.mkdir(parents=True, exist_ok=True)
        else:
            if not dst_path.parent.exists():
                dst_path.parent.mkdir(parents=True, exist_ok=True)
            if overwrite or not dst_path.exists():
                shutil.copy(str(src_path), str(dst_path))
