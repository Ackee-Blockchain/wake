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
    from woke.testing.debugging import attach_debugger, set_exception_handler
    from woke.testing.pytest_plugin import PytestWokePlugin

    config = WokeConfig(woke_root_path=context.obj["woke_root_path"])
    config.load_configs()  # load ~/.woke/config.toml and ./woke.toml

    if len(test_path) == 0:
        test_path = ("tests/",)

    if debug:
        set_exception_handler(attach_debugger)

    sys.exit(pytest.main(list(test_path) + ["-s"], plugins=[PytestWokePlugin(config)]))
