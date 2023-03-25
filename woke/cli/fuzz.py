import importlib.resources
import importlib.util
import inspect
import multiprocessing
import shutil
import sys
from pathlib import Path
from typing import Callable, Iterable, Tuple

import rich_click as click

from woke.config import WokeConfig

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
@click.option(
    "--coverage",
    type=int,
    is_flag=False,
    flag_value=-1,
    default=0,
    help="Number of processes to report coverage (0 = off).",
)
@click.option("--seed", "-s", "seeds", multiple=True, type=str, help="Random seeds")
@click.option(
    "--passive",
    is_flag=True,
    default=False,
    help="Print one process output into console, run other in background.",
)
@click.pass_context
def run_fuzz(
    ctx: click.Context,
    paths: Tuple[str],
    process_count: int,
    coverage: int,
    seeds: Tuple[str],
    passive: bool,
) -> None:
    """Run a Woke test using multiple processes."""

    from woke.testing.fuzzing.fuzzer import fuzz

    if coverage == -1:
        coverage = process_count

    if process_count < coverage:
        raise ValueError("Coverage must be less than or equal to process count.")

    config = WokeConfig()
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

    logs_dir = config.project_root_path / ".woke-logs" / "fuzz"
    shutil.rmtree(logs_dir, ignore_errors=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    try:
        for func in fuzz_functions:
            console.print("\n\n")
            console.print(f"Fuzzing '{func.__name__}' in '{func.__module__}'.")
            fuzz(
                config,
                func,
                process_count,
                random_seeds,
                logs_dir,
                passive,
                coverage,
                False,
            )
    except Exception as e:
        console.print_exception()
        sys.exit(1)
