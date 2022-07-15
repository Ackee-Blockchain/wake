import importlib.resources
import importlib.util
import inspect
import multiprocessing
import platform
import sys
import time
from pathlib import Path
from typing import Callable, Iterable, Tuple

import click

from woke.config import WokeConfig
from woke.fuzzer import fuzz

from .console import console


def _get_module_name(path: Path, root: Path) -> str:
    path = path.with_suffix("")
    return ".".join(path.relative_to(root).parts)


@click.command(name="fuzz")
@click.argument("paths", nargs=-1, type=click.Path(exists=True))
@click.option(
    "--process-count",
    "-n",
    default=(multiprocessing.cpu_count()),
    help="Number of processes to create for fuzzing.",
)
@click.option("--seed", "-s", "seeds", multiple=True, type=str, help="Random seeds")
@click.option(
    "--passive",
    is_flag=True,
    default=False,
    help="Print one process output into console, run other in background.",
)
@click.option(
    "--network",
    type=str,
    default="development",
    help="Choose brownie dev chain. Default is 'development' for ganache",
)
@click.pass_context
def run_fuzz(
    ctx: click.Context,
    paths: Tuple[str],
    process_count: int,
    seeds: Tuple[str],
    passive: bool,
    network: str,
) -> None:
    """Run Woke fuzzer."""
    config = WokeConfig(woke_root_path=ctx.obj["woke_root_path"])
    config.load_configs()  # load ~/.woke/config.toml and ./woke.toml

    random_seeds = [bytes.fromhex(seed) for seed in seeds]
    if len(paths) == 0:
        paths = (str(config.project_root_path / "tests"),)

    py_files = set()

    for path in paths:
        fuzz_path = Path(path).resolve()

        if fuzz_path.is_file() and fuzz_path.match("*.py"):
            py_files.add(fuzz_path)
        elif fuzz_path.is_dir():
            for p in fuzz_path.rglob("test_*.py"):
                if p.is_file():
                    py_files.add(p)
        else:
            raise ValueError(f"'{fuzz_path}' is not a Python file or directory.")

    fuzz_functions = []

    sys.path.insert(0, str(config.project_root_path))
    for file in py_files:
        module_name = _get_module_name(file, config.project_root_path)
        module_spec = importlib.util.spec_from_file_location(module_name, file)
        if module_spec is None or module_spec.loader is None:
            raise ValueError()
        module = importlib.util.module_from_spec(module_spec)
        sys.modules[module_name] = module
        module_spec.loader.exec_module(module)

        functions: Iterable[Callable] = (
            func
            for _, func in inspect.getmembers(module, inspect.isfunction)
            if func.__module__ == module_name and func.__name__.startswith("test")
        )
        for func in functions:
            console.print(
                f"Found '{func.__name__}' function in '{func.__module__}' file."
            )
            fuzz_functions.append(func)

    logs_dir = config.project_root_path / ".woke-logs" / "fuzz" / str(int(time.time()))
    logs_dir.mkdir(parents=True, exist_ok=False)
    latest_dir = logs_dir.parent / "latest"

    # create `latest` symlink
    if platform.system() != "Windows":
        if latest_dir.is_symlink():
            latest_dir.unlink()
        latest_dir.symlink_to(logs_dir, target_is_directory=True)

    for func in fuzz_functions:
        console.print("\n\n")
        console.print(f"Fuzzing '{func.__name__}' in '{func.__module__}'.")
        fuzz(config, func, process_count, random_seeds, logs_dir, passive, network)
