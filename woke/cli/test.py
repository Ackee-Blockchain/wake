import json
import sys
from typing import Tuple

import rich_click as click


@click.command(name="test")
@click.option(
    "--debug", "-d", is_flag=True, default=False, help="Attach debugger on exception."
)
@click.option(
    "--s/--no-s",
    "-s",
    is_flag=True,
    default=True,
    help="Show stdout and stderr of test.",
)
@click.option(
    "--coverage/--no-coverage",
    is_flag=True,
    default=False,
    help="Create coverage report.",
)
@click.argument("pytest_args", nargs=-1, type=click.UNPROCESSED)
@click.pass_context
def run_test(
    context: click.Context,
    debug: bool,
    s: bool,
    coverage: bool,
    pytest_args: Tuple[str, ...],
) -> None:
    """Execute Woke tests using pytest."""
    import pytest

    from woke.config import WokeConfig
    from woke.development.globals import set_config
    from woke.testing.pytest_plugin import PytestWokePlugin

    config = WokeConfig()
    config.load_configs()  # load ~/.woke/config.toml and ./woke.toml

    set_config(config)

    if debug:
        from woke.development.globals import attach_debugger, set_exception_handler

        set_exception_handler(attach_debugger)

    if coverage:
        from woke.development.globals import set_coverage_handler
        from woke.testing.coverage import CoverageHandler

        set_coverage_handler(CoverageHandler(config))

    args = list(pytest_args)
    if s:
        args.append("-s")

    # disable pytest-brownie
    args.append("-p")
    args.append("no:pytest-brownie")

    # disable ape_test
    args.append("-p")
    args.append("no:ape_test")

    # disable pytest_ethereum
    args.append("-p")
    args.append("no:pytest_ethereum")

    ret = pytest.main(args, plugins=[PytestWokePlugin(config)])

    if coverage:
        from woke.development.globals import get_coverage_handler
        from woke.testing.coverage import export_merged_ide_coverage, write_coverage

        coverage_handler = get_coverage_handler()
        assert coverage_handler is not None

        c = export_merged_ide_coverage([coverage_handler.get_contract_ide_coverage()])
        write_coverage(c, config.project_root_path / "woke-coverage.cov")

    sys.exit(ret)
