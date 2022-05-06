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
@click.argument("files", nargs=-1, type=click.Path(exists=True))
@click.option(
    "--process-count",
    default=(multiprocessing.cpu_count()),
    help="Number of processes to create for fuzzing.",
)
@click.pass_context
def run_fuzz(ctx: click.Context, files: Tuple[str], process_count: int) -> None:
    """Run Woke fuzzer."""
    config = WokeConfig(woke_root_path=ctx.obj["woke_root_path"])
    config.load_configs()  # load ~/.woke/config.toml and ./woke.toml

    if len(files) == 0:
        raise ValueError("No test files provided.")

    for file in files:
        fuzz_file = Path(file)
        if not fuzz_file.is_file() or not fuzz_file.match("*.py"):
            raise ValueError(f"'{fuzz_file}' is not a Python file.")

        module_spec = importlib.util.spec_from_file_location(MODULE_NAME, fuzz_file)
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
            console.print(f"Found '{func.__name__}' function in '{fuzz_file}' file.")
            fuzz(config, func, process_count)
