from __future__ import annotations

import random
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Iterable, List, Optional, Tuple

import click.shell_completion as shell_completion
import rich_click as click

if TYPE_CHECKING:
    from wake.config import WakeConfig


def _get_module_name(path: Path, root: Path) -> str:
    path = path.with_suffix("")
    return ".".join(path.relative_to(root).parts)


def run_no_pytest(
    config: WakeConfig,
    debug: bool,
    proc_count: int,
    coverage: int,
    random_seeds: List[bytes],
    attach_first: bool,
    args: Tuple[str, ...],
) -> None:
    import importlib.util
    import inspect
    import shutil

    from wake.development.globals import (
        attach_debugger,
        chain_interfaces_manager,
        get_coverage_handler,
        reset_exception_handled,
        set_coverage_handler,
        set_exception_handler,
    )
    from wake.testing.coverage import (
        CoverageHandler,
        export_merged_ide_coverage,
        write_coverage,
    )
    from wake.testing.fuzzing.fuzzer import fuzz

    from .console import console

    if len(args) == 0:
        args = (str(config.project_root_path / "tests"),)

    # discover all test functions
    py_files = set()
    for path in args:
        test_path = Path(path).resolve()

        if test_path.is_file() and test_path.match("*.py"):
            py_files.add(test_path)
        elif test_path.is_dir():
            for p in test_path.rglob("test_*.py"):
                if p.is_file():
                    py_files.add(p)
        else:
            raise ValueError(f"'{test_path}' is not a Python file or directory.")

    test_functions = []
    for file in py_files:
        module_name = _get_module_name(file, config.project_root_path)
        module_spec = importlib.util.spec_from_file_location(module_name, file)
        if module_spec is None or module_spec.loader is None:
            raise ValueError()
        module = importlib.util.module_from_spec(module_spec)
        sys.modules[module_name] = module
        module_spec.loader.exec_module(module)

        functions: Iterable[Tuple[str, Callable]] = (
            (func_name, func)
            for func_name, func in inspect.getmembers(module, inspect.isfunction)
            if func.__module__ == module_name and func_name.startswith("test")
        )
        for func_name, func in functions:
            console.print(f"Found '{func_name}' function in '{func.__module__}' file.")
            test_functions.append((func_name, func))

    if proc_count == 1:
        random.seed(random_seeds[0])
        console.print(f"Using random seed {random_seeds[0].hex()}")

        if debug:
            set_exception_handler(attach_debugger)

        if coverage:
            set_coverage_handler(CoverageHandler(config))

        try:
            for _, func in test_functions:
                try:
                    func()
                except Exception:
                    if debug:
                        attach_debugger(*sys.exc_info())
                    raise
                reset_exception_handled()
        finally:
            if coverage:
                coverage_handler = get_coverage_handler()
                assert coverage_handler is not None

                c = export_merged_ide_coverage(
                    [coverage_handler.get_contract_ide_coverage()]
                )
                write_coverage(c, config.project_root_path / "wake-coverage.cov")

            chain_interfaces_manager.close_all()
    else:
        logs_dir = config.project_root_path / ".wake" / "logs" / "testing"
        shutil.rmtree(logs_dir, ignore_errors=True)
        logs_dir.mkdir(parents=True, exist_ok=True)

        try:
            for func_name, func in test_functions:
                console.print("\n\n")
                console.print(f"Running '{func_name}' in '{func.__module__}'.")
                fuzz(
                    config,
                    func_name,
                    func,
                    proc_count,
                    random_seeds,
                    logs_dir,
                    attach_first,
                    coverage,
                    False,
                )
        except Exception as e:
            console.print_exception()
            sys.exit(1)


class FileAndPassParamType(click.ParamType):
    name = "file_and_pass"

    def convert(self, value, param, ctx):
        return value

    def shell_complete(
        self, ctx: click.Context, param: click.Parameter, incomplete: str
    ) -> List:
        return [shell_completion.CompletionItem(incomplete, type="file")]


@click.command(
    name="test",
    context_settings=dict(
        ignore_unknown_options=True,
    ),
)
@click.option(
    "--debug",
    "-d",
    is_flag=True,
    default=False,
    help="Attach debugger on exception. Only if --proc is not set.",
)
@click.option(
    "--s/--no-s",
    "-s",
    is_flag=True,
    default=True,
    help="Show stdout and stderr of test.",
)
@click.option(
    "--proc",
    "-P",
    "proc_count",
    type=int,
    is_flag=False,
    flag_value=-1,
    default=None,
    help="Run tests in multiple processes.",
)
@click.option(
    "--coverage",
    "--cov",
    type=int,
    is_flag=False,
    flag_value=-1,
    default=0,
    help="Number of processes to report coverage (0 = off).",
)
@click.option(
    "--no-pytest",
    is_flag=True,
    default=False,
    help="Don't use pytest to run tests.",
)
@click.option(
    "--seed",
    "-S",
    "seeds",
    multiple=True,
    type=str,
    help="Random seeds",
)
@click.option(
    "--attach-first",
    is_flag=True,
    default=False,
    help="In multi-process mode, print stdout of first process to console and don't prompt on exception in other processes.",
)
@click.option(
    "--dist",
    type=click.Choice(["uniform", "duplicated"]),
    default="duplicated",
    help="Distribution of test cases to processes.",
)
@click.option(
    "-v",
    "--verbosity",
    default=0,
    count=True,
    help="Increase verbosity. Can be specified multiple times.",
)
@click.argument("paths_or_pytest_args", nargs=-1, type=FileAndPassParamType())
@click.pass_context
def run_test(
    context: click.Context,
    debug: bool,
    s: bool,
    proc_count: Optional[int],
    coverage: int,
    no_pytest: bool,
    seeds: Tuple[str],
    attach_first: bool,
    dist: str,
    verbosity: int,
    paths_or_pytest_args: Tuple[str, ...],
) -> None:
    """Execute Wake tests using pytest."""
    import os

    import pytest

    from wake.config import WakeConfig
    from wake.development.globals import set_config, set_verbosity

    if proc_count == -1:
        proc_count = os.cpu_count()
    elif proc_count is None:
        proc_count = 1
    assert proc_count is not None

    if coverage > proc_count:
        raise click.BadParameter(
            "Coverage process count must be less than or equal to process count."
        )

    if attach_first and debug:
        raise click.BadParameter(
            "--attach-first and --debug cannot be used at the same time."
        )

    try:
        random_seeds = [bytes.fromhex(seed) for seed in seeds]
    except ValueError:
        raise click.BadParameter("Seeds must be hex numbers.")

    config = WakeConfig(local_config_path=context.obj.get("local_config_path", None))
    config.load_configs()

    set_config(config)
    sys.path.insert(0, str(config.project_root_path))

    set_verbosity(verbosity)

    # generate remaining random seeds
    if len(random_seeds) < proc_count:
        for i in range(proc_count - len(random_seeds)):
            random_seeds.append(os.urandom(8))

    if no_pytest:
        run_no_pytest(
            config,
            debug,
            proc_count,
            coverage,
            random_seeds,
            attach_first,
            paths_or_pytest_args,
        )
    else:
        pytest_args = list(paths_or_pytest_args)

        if verbosity > 0:
            pytest_args.append("-" + "v" * verbosity)

        if s:
            pytest_args.append("-s")

        # disable pytest-brownie
        pytest_args.append("-p")
        pytest_args.append("no:pytest-brownie")

        # disable ape_test
        pytest_args.append("-p")
        pytest_args.append("no:ape_test")

        # disable pytest_ethereum
        pytest_args.append("-p")
        pytest_args.append("no:pytest_ethereum")

        if proc_count > 1:
            from wake.testing.pytest_plugin_multiprocess_server import (
                PytestWakePluginMultiprocessServer,
            )

            sys.exit(
                pytest.main(
                    pytest_args,
                    plugins=[
                        PytestWakePluginMultiprocessServer(
                            config,
                            coverage,
                            proc_count,
                            random_seeds,
                            attach_first,
                            debug,
                            dist,
                            pytest_args,
                        )
                    ],
                )
            )
        else:
            from wake.testing.pytest_plugin_single import PytestWakePluginSingle

            sys.exit(
                pytest.main(
                    pytest_args,
                    plugins=[
                        PytestWakePluginSingle(config, debug, coverage, random_seeds)
                    ],
                )
            )
