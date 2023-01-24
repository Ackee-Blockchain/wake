import sys
from typing import Tuple

import rich_click as click


@click.command(name="test")
@click.argument("test_path", nargs=-1, type=click.Path(exists=True))
@click.option("--debug", "-d", is_flag=True, default=False)
@click.pass_context
def run_test(context: click.Context, test_path: Tuple[str, ...], debug: bool) -> None:
    import pytest

    from woke.config import WokeConfig
    from woke.testing.globals import set_config
    from woke.testing.pytest_plugin import PytestWokePlugin

    config = WokeConfig()
    config.load_configs()  # load ~/.woke/config.toml and ./woke.toml

    set_config(config)

    if len(test_path) == 0:
        test_path = ("tests/",)

    if debug:
        from woke.testing.globals import attach_debugger, set_exception_handler

        set_exception_handler(attach_debugger)

    sys.exit(pytest.main(list(test_path) + ["-s"], plugins=[PytestWokePlugin(config)]))
