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
    "-RS",
    "--random-state",
    type=str,
    help="Input random state json path.",
    is_flag=False,
    flag_value="0",
    default=None,
    required=False,
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
    "--shrink-exact-flow/--no-shrink-exact-flow",
    default=False,
    help="When shrinking, wait for the error to happen in the same flow (not earlier or later).",
)
@click.option(
    "--shrink-exact-exception/--no-shrink-exact-exception",
    default=False,
    help="When shrinking, only accept exactly matching exceptions (i.e. including same arguments).",
)
@click.option(
    "--shrink-target-invariants-only/--shrink-all-invariants",
    default=False,
    help="When shrinking, check only target invariants for faster fuzzing.",
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
@click.argument("paths_or_pytest_args", nargs=-1, type=FileAndPassParamType())
@click.pass_context
def run_test(
    context: click.Context,
    debug: bool,
    s: bool,
    proc_count: Optional[int],
    coverage: int,
    seeds: Tuple[str],
    attach_first: bool,
    dist: str,
    verbosity: int,
    random_state: Optional[str],
    shrink: Optional[str],
    shrink_exact_flow: bool,
    shrink_exact_exception: bool,
    shrink_target_invariants_only: bool,
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

        if shrink is not None:
            raise click.BadParameter("Shrink can not execute with multiprocess mode.")

        if shrank is not None:
            raise click.BadParameter(
                "Shrank reproduce can not execute with multiprocess mode."
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
        from wake.development.globals import (
            set_shrink_exact_exception,
            set_shrink_exact_flow,
            set_shrink_target_invariants_only,
        )
        from wake.testing.pytest_plugin_single import PytestWakePluginSingle

        test_mode = 0
        test_info_path = ""
        if random_state is not None:
            test_info_path = random_state
            test_mode = 3
        if shrink is not None:
            test_info_path = shrink
            test_mode = 1
            set_shrink_exact_flow(shrink_exact_flow)
            set_shrink_exact_exception(shrink_exact_exception)
            set_shrink_target_invariants_only(shrink_target_invariants_only)
        if shrank:
            test_mode = 2
            test_info_path = shrank
        sys.exit(
            pytest.main(
                pytest_args,
                plugins=[
                    PytestWakePluginSingle(
                        config, debug, coverage, random_seeds, test_mode, test_info_path
                    )
                ],
            )
        )
