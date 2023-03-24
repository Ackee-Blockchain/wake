import json
import sys
from typing import Tuple

import rich_click as click


@click.command(name="test")
@click.argument("test_path", nargs=-1, type=click.Path(exists=True))
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
@click.pass_context
def run_test(
    context: click.Context,
    test_path: Tuple[str, ...],
    debug: bool,
    s: bool,
    coverage: bool,
) -> None:
    """Execute Woke tests using pytest."""
    import pytest

    from woke.config import WokeConfig
    from woke.development.globals import set_config
    from woke.testing.pytest_plugin import PytestWokePlugin

    config = WokeConfig()
    config.load_configs()  # load ~/.woke/config.toml and ./woke.toml

    set_config(config)

    if len(test_path) == 0:
        test_path = ("tests/",)

    if debug:
        from woke.development.globals import attach_debugger, set_exception_handler

        set_exception_handler(attach_debugger)

    if coverage:
        from woke.development.globals import set_coverage_handler
        from woke.testing.coverage import CoverageHandler

        set_coverage_handler(CoverageHandler(config))

    args = list(test_path)
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

        coverage_handler = get_coverage_handler()
        assert coverage_handler is not None

        data = {
            str(k): [i.export() for i in v.values()]
            for k, v in coverage_handler.get_contract_ide_coverage().items()
        }
        (config.project_root_path / "woke.cov").write_text(json.dumps(data, indent=4))

    sys.exit(ret)
