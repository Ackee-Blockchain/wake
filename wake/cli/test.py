import sys
from typing import List, Tuple

import click.shell_completion as shell_completion
import rich_click as click


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
@click.argument("pytest_args", nargs=-1, type=FileAndPassParamType())
@click.pass_context
def run_test(
    context: click.Context,
    debug: bool,
    s: bool,
    coverage: bool,
    pytest_args: Tuple[str, ...],
) -> None:
    """Execute Wake tests using pytest."""
    import pytest

    from wake.config import WakeConfig
    from wake.development.globals import chain_interfaces_manager, set_config
    from wake.testing.pytest_plugin import PytestWakePlugin

    config = WakeConfig(local_config_path=context.obj.get("local_config_path", None))
    config.load_configs()

    set_config(config)

    if debug:
        from wake.development.globals import attach_debugger, set_exception_handler

        set_exception_handler(attach_debugger)

    if coverage:
        from wake.development.globals import set_coverage_handler
        from wake.testing.coverage import CoverageHandler

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

    sys.path.insert(0, str(config.project_root_path))

    ret = pytest.main(args, plugins=[PytestWakePlugin(config)])

    if coverage:
        from wake.development.globals import get_coverage_handler
        from wake.testing.coverage import export_merged_ide_coverage, write_coverage

        coverage_handler = get_coverage_handler()
        assert coverage_handler is not None

        c = export_merged_ide_coverage([coverage_handler.get_contract_ide_coverage()])
        write_coverage(c, config.project_root_path / "wake-coverage.cov")

    chain_interfaces_manager.close_all()

    sys.exit(ret)
