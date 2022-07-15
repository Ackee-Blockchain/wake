import pathlib
import shutil


def copy_dir(
    src_dir: pathlib.Path, dst_dir: pathlib.Path, overwrite: bool = False
) -> None:
    """
    Copies contents of directory and creates dst_dir if it doesn't exist.
    Overwrites files if overwrite is True, otherwise raises FileExistsError if existing files
    are found
    """
    dst_dir.mkdir(exist_ok=True)
    src_dst_paths = [
        (p.absolute(), dst_dir / p.relative_to(src_dir)) for p in src_dir.rglob("*")
    ]
    if not overwrite:
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
            shutil.copy(str(src_path), str(dst_path))
