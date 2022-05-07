import inspect
import importlib.resources
import importlib.util
import multiprocessing
from pathlib import Path
from typing import Tuple, Callable, Iterable

import click

from woke.a_config import WokeConfig
from woke.m_fuzz import fuzz
from .console import console

MODULE_NAME = "woke_fuzz_tests"


@click.command(name="fuzz")
@click.argument("paths", nargs=-1, type=click.Path(exists=True))
@click.option(
    "--process-count",
    default=(multiprocessing.cpu_count()),
    help="Number of processes to create for fuzzing.",
)
@click.option("--seed", "-s", "seeds", multiple=True, type=str, help="Random seeds")
@click.pass_context
def run_fuzz(
    ctx: click.Context, paths: Tuple[str], process_count: int, seeds: Tuple[str]
) -> None:
    """Run Woke fuzzer."""
    config = WokeConfig(woke_root_path=ctx.obj["woke_root_path"])
    config.load_configs()  # load ~/.woke/config.toml and ./woke.toml

    random_seeds = [bytes.fromhex(seed) for seed in seeds]
    if len(paths) == 0:
        paths = (str(config.project_root_path / "test"),)

    py_files = []

    for path in paths:
        fuzz_path = Path(path)

        if fuzz_path.is_file() and fuzz_path.match("*.py"):
            py_files.append(fuzz_path)
        elif fuzz_path.is_dir():
            for p in fuzz_path.rglob("*.py"):
                if p.is_file():
                    py_files.append(p)
        else:
            raise ValueError(f"'{fuzz_path}' is not a Python file or directory.")

    fuzz_functions = []

    for file in py_files:
        module_spec = importlib.util.spec_from_file_location(MODULE_NAME, file)
        if module_spec is None or module_spec.loader is None:
            raise ValueError()
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)

        functions: Iterable[Callable] = (
            func
            for _, func in inspect.getmembers(module, inspect.isfunction)
            if func.__module__ == MODULE_NAME and func.__name__.startswith("test")
        )
        for func in functions:
            console.print(f"Found '{func.__name__}' function in '{file}' file.")
            fuzz_functions.append(func)

    for func in fuzz_functions:
        fuzz(config, func, process_count, random_seeds)
