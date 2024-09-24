from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Iterable, List, Optional, Tuple

import click.shell_completion as shell_completion
import rich_click as click

import pickle

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
    random_states: Optional[List[bytes]],
    attach_first: bool,
    args: Tuple[str, ...],
) -> None:
    import importlib.util
    import inspect
    import shutil
    from functools import partial

    from wake.development.globals import (
        attach_debugger,
        chain_interfaces_manager,
        get_coverage_handler,
        random,
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

        if random_states:
            random.setstate(pickle.loads(random_states[0]))
            console.print(f"Using random state {random_states[0].hex()}")
        else:
            random.seed(random_seeds[0])
            console.print(f"Using random seed {random_seeds[0].hex()}")

        if debug:
            set_exception_handler(partial(attach_debugger, seed=random_seeds[0]))

        if coverage:
            set_coverage_handler(CoverageHandler(config))

        try:
            for _, func in test_functions:
                try:
                    func()
                except Exception:
                    if debug:
                        attach_debugger(*sys.exc_info(), seed=random_seeds[0])
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
                    random_states,
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
    "--random-state",
    "-RS",
    "random_states",
    multiple=True,
    type=str,
    help="Random statuses",
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
@click.option(
    "-SH",
    "--shrink",
    # Didn't use click.Path since we accept relative index of crash log file
    type=str,
    help="Path to the shrink log file.",
    is_flag=False,
    flag_value=0,
    default=None,
)

@click.option(
    "-SR",
    "--shrank",
    "--reproduce",
    # Didn't use click.Path since we accept relative index of crash log file
    type=str,
    help="Path of shrank file.",
    is_flag=False,
    flag_value=0,
    default=None,
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
    random_states: Tuple[str],
    attach_first: bool,
    dist: str,
    verbosity: int,
    shrink: Optional[str],
    shrank: Optional[str],
    paths_or_pytest_args: Tuple[str, ...],
) -> None:
    """Execute Wake tests using pytest."""
    import os

    import pytest

    from wake.config import WakeConfig
    from wake.development.globals import set_config, set_verbosity

    if proc_count == -1:
        proc_count = os.cpu_count()
    if coverage == -1:
        coverage = proc_count or 1

    if coverage > (proc_count or 1):
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

    try:
        random_states_byte = [bytes.fromhex(random_state) for random_state in random_states]
    except ValueError:
        raise click.BadParameter("Random states must be hex numbers.")

    config = WakeConfig(local_config_path=context.obj.get("local_config_path", None))
    config.load_configs()

    set_config(config)
    sys.path.insert(0, str(config.project_root_path))

    set_verbosity(verbosity)

    # generate remaining random seeds
    if len(random_seeds) < (proc_count or 1):
        for i in range((proc_count or 1) - len(random_seeds)):
            random_seeds.append(os.urandom(8))

    if no_pytest:
        pass
    else:
        pytest_path_specified = False
        if len(paths_or_pytest_args) > 0:
            pytest_path_specified = True
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

        if proc_count is not None:
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
                            random_states_byte,
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
            from wake.development.globals import set_fuzz_mode,set_sequence_initial_internal_state, set_error_flow_num, set_shrank_path, get_config
            def extract_test_path(crash_log_file_path):
                if crash_log_file_path is not None:
                    with open(crash_log_file_path, 'r') as file:
                        for line in file:
                            if "Current test file" in line:
                                # Extract the part after the colon
                                parts = line.split(":")
                                if len(parts) == 2:
                                    return parts[1].strip()
                return None

            def extract_executed_flow_number(crash_log_file_path):
                if crash_log_file_path is not None:
                    with open(crash_log_file_path, 'r') as file:
                        for line in file:
                            if "executed flow number" in line:
                                # Extract the number after the colon
                                parts = line.split(":")
                                if len(parts) == 2:
                                    try:
                                        executed_flow_number = int(parts[1].strip())
                                        return executed_flow_number
                                    except ValueError:
                                        pass  # Handle the case where the value after ":" is not an integer
                return None

            def extract_internal_state(crash_log_file_path):
                if crash_log_file_path is not None:
                    with open(crash_log_file_path, 'r') as file:
                        for line in file:
                            if "Internal state of beginning of sequence" in line:
                                # Extract the part after the colon
                                parts = line.split(":")
                                if len(parts) == 2:
                                    hex_string = parts[1].strip()
                                    try:
                                        # Convert the hex string to bytes
                                        internal_state_bytes = bytes.fromhex(hex_string)
                                        return internal_state_bytes
                                    except ValueError:
                                        pass  # Handle the case where the value after ":" is not a valid hex string
                return None

            def get_shrink_argument_path(shrink_path_str) -> Path:
                try:
                    path = Path(shrink_path_str)
                    if not path.exists():
                        raise ValueError(f"Shrink log not found: {path}")
                    return path
                except ValueError:
                    pass

                crash_logs_dir = get_config().project_root_path / ".wake" / "logs" / "crashes"
                if not crash_logs_dir.exists():
                    raise click.BadParameter(f"Crash logs directory not found: {crash_logs_dir}")
                index = int(shrink_path_str)
                crash_logs = sorted(crash_logs_dir.glob("*.txt"), key=os.path.getmtime, reverse=True)
                if abs(index) > len(crash_logs):
                    raise click.BadParameter(f"Invalid crash log index: {index}")
                return Path(crash_logs[index])

            def get_shrank_argument_path(shrank_path_str) -> Path:
                try:
                    shrank_path = Path(shrank_path_str)
                    if not shrank_path.exists():
                        raise ValueError(f"Shrank data file not found: {shrank_path}")
                    return shrank_path
                except ValueError:
                    pass
                shrank_data_path = get_config().project_root_path / ".wake" / "logs" / "shrank"
                if not shrank_data_path.exists():
                    raise click.BadParameter(f"Shrank data file not found: {shrank_data_path}")

                index = int(shrank_path_str)
                shrank_files = sorted(shrank_data_path.glob("*.bin"), key=os.path.getmtime, reverse=True)
                if abs(index) > len(shrank_files):
                    raise click.BadParameter(f"Invalid crash log index: {index}")
                return Path(shrank_files[index])




            if shrank is not None and shrink is not None:
                raise click.BadParameter("Both shrink and shrieked cannot be provided at the same time.")

            if shrink is not None:
                shrink_crash_path = get_shrink_argument_path(shrink)
                path = extract_test_path(shrink_crash_path)
                number = extract_executed_flow_number(shrink_crash_path)
                assert number is not None, "Unexpected file format"
                set_fuzz_mode(1)
                set_error_flow_num(number)
                beginning_random_state_bytes = extract_internal_state(shrink_crash_path)
                assert beginning_random_state_bytes is not None, "Unexpected file format"
                set_sequence_initial_internal_state(beginning_random_state_bytes)
                if pytest_path_specified:
                    assert path == pytest_args[0], "crash log file path must be same as the test file path in pytest_args"
                else:
                    pytest_args.insert(0, path)

            if shrank:
                set_fuzz_mode(2)
                shrank_data_path = get_shrank_argument_path(shrank)
                from wake.testing.fuzzing.fuzz_shrink import ShrankInfoFile
                with open(shrank_data_path, 'rb') as f:
                    store_data: ShrankInfoFile = pickle.load(f)
                target_fuzz_path = store_data.target_fuzz_path
                if pytest_path_specified:
                    assert target_fuzz_path == pytest_args[0], "Shrank data file path must be same as the test file path in pytest_args"
                else:
                    pytest_args.insert(0, target_fuzz_path)
                set_shrank_path(shrank_data_path)
            sys.exit(
                pytest.main(
                    pytest_args,
                    plugins=[
                        PytestWakePluginSingle(config, debug, coverage, random_seeds, random_states_byte)
                    ],
                )
            )
