from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional, Tuple

import click.shell_completion as shell_completion
import rich_click as click

if TYPE_CHECKING:
    from wake.config import WakeConfig


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
    flag_value="0",
    default=None,
    required=False,
)
@click.option(
    "-SR",
    "--shrank",
    "--reproduce",
    # Didn't use click.Path since we accept relative index of crash log file
    type=str,
    help="Path of shrank file.",
    is_flag=False,
    flag_value="0",
    default=None,
    required=False,
)
@click.option(
    "-SF",
    "--step-flow",
    type=str,
    help="Path to the crash log file.",
    is_flag=False,
    flag_value="0",
    default=None,
    required=False,
)
@click.argument("paths_or_pytest_args", nargs=-1, type=FileAndPassParamType())
@click.pass_context
def run_test(
    context: click.Context,
    debug: bool,
    s: bool,
    proc_count: Optional[int],
    coverage: int,
    seeds: Tuple[str],
    random_states: Tuple[str],
    attach_first: bool,
    dist: str,
    verbosity: int,
    shrink: Optional[str],
    shrank: Optional[str],
    step_flow: Optional[str],
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
        random_states_byte = [
            bytes.fromhex(random_state) for random_state in random_states
        ]
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

        from wake.development.globals import (
            get_config,
            set_error_flow_num,
            set_fuzz_mode,
            set_sequence_initial_internal_state,
            set_shrank_path,
        )
        from wake.testing.pytest_plugin_single import PytestWakePluginSingle

        def get_single_test_path(args: list[str]) -> tuple[bool, str | None]:
            has_path = False
            path = None
            for arg in args:
                if Path(arg).exists():
                    if has_path:
                        raise click.BadParameter(
                            "Multiple test files specified for shrinking"
                        )
                    has_path = True
                    path = arg
            return has_path, path

        def extract_test_path(crash_log_file_path: Path) -> str:
            if crash_log_file_path is not None:
                with open(crash_log_file_path, "r") as file:
                    for line in file:
                        if "Current test file" in line:
                            # Extract the part after the colon
                            parts = line.split(":")
                            if len(parts) == 2:
                                return parts[1].strip()
            raise ValueError("Unexpected file format")

        def extract_executed_flow_number(crash_log_file_path: Path) -> int:
            if crash_log_file_path is not None:
                with open(crash_log_file_path, "r") as file:
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
            raise ValueError("Unexpected file format")

        def extract_internal_state(crash_log_file_path: Path) -> bytes:
            if crash_log_file_path is not None:
                with open(crash_log_file_path, "r") as file:
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
            raise ValueError("Unexpected file format")

        def get_shrink_argument_path(shrink_path_str: str) -> Path:
            try:
                path = Path(shrink_path_str)
                if not path.exists():
                    raise ValueError(f"Shrink log not found: {path}")
                return path
            except ValueError:
                pass

            crash_logs_dir = (
                get_config().project_root_path / ".wake" / "logs" / "crashes"
            )
            if not crash_logs_dir.exists():
                raise click.BadParameter(
                    f"Crash logs directory not found: {crash_logs_dir}"
                )
            index = int(shrink_path_str)
            crash_logs = sorted(
                crash_logs_dir.glob("*.txt"), key=os.path.getmtime, reverse=True
            )
            if abs(index) > len(crash_logs):
                raise click.BadParameter(f"Invalid crash log index: {index}")
            return Path(crash_logs[index])

        def get_shrank_argument_path(shrank_path_str: str) -> Path:
            try:
                shrank_path = Path(shrank_path_str)
                if not shrank_path.exists():
                    raise ValueError(f"Shrank data file not found: {shrank_path}")
                return shrank_path
            except ValueError:
                pass
            shrank_data_path = (
                get_config().project_root_path / ".wake" / "logs" / "shrank"
            )
            if not shrank_data_path.exists():
                raise click.BadParameter(
                    f"Shrank data file not found: {shrank_data_path}"
                )

            index = int(shrank_path_str)
            shrank_files = sorted(
                shrank_data_path.glob("*.bin"), key=os.path.getmtime, reverse=True
            )
            if abs(index) > len(shrank_files):
                raise click.BadParameter(f"Invalid crash log index: {index}")
            return Path(shrank_files[index])

        if shrank is not None and shrink is not None:
            raise click.BadParameter(
                "Both shrink and shrieked cannot be provided at the same time."
            )

        if step_flow is not None and shrank is not None:
            raise click.BadParameter(
                "Both step-flow and shrank cannot be provided at the same time."
            )

        if step_flow and shrink is not None:
            raise click.BadParameter(
                "Both step-flow and shrink cannot be provided at the same time."
            )

        if shrink is not None or step_flow is not None:
            if step_flow:
                set_fuzz_mode(3)
                argument_path = step_flow
            else:
                assert shrink is not None, "Shrink must be provided when step-flow is not used"
                set_fuzz_mode(1)
                argument_path = shrink

            pytest_path_specified, test_path = get_single_test_path(pytest_args)
            shrink_crash_path = get_shrink_argument_path(argument_path)
            path = extract_test_path(shrink_crash_path)
            number = extract_executed_flow_number(shrink_crash_path)
            set_error_flow_num(number)
            beginning_random_state_bytes = extract_internal_state(shrink_crash_path)
            set_sequence_initial_internal_state(beginning_random_state_bytes)
            if pytest_path_specified:
                assert (
                    path == test_path
                ), "crash log file path must be same as the test file path in pytest_args"
            else:
                pytest_args.insert(0, path)

        if shrank:
            import pickle
            from wake.testing.fuzzing.fuzz_shrink import ShrankInfoFile

            set_fuzz_mode(2)
            pytest_path_specified, test_path = get_single_test_path(pytest_args)
            shrank_data_path = get_shrank_argument_path(shrank)

            set_fuzz_mode(2)
            pytest_path_specified, test_path = get_single_test_path(pytest_args)
            shrank_data_path = get_shrank_argument_path(shrank)

            with open(shrank_data_path, "rb") as f:
                store_data: ShrankInfoFile = pickle.load(f)
            target_fuzz_path = store_data.target_fuzz_path
            if pytest_path_specified:
                assert (
                    target_fuzz_path == test_path
                ), "Shrank data file path must be same as the test file path in pytest_args"
            else:
                pytest_args.insert(0, target_fuzz_path)
            set_shrank_path(shrank_data_path)
        sys.exit(
            pytest.main(
                pytest_args,
                plugins=[
                    PytestWakePluginSingle(
                        config, debug, coverage, random_seeds, random_states_byte
                    )
                ],
            )
        )
