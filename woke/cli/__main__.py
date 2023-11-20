import asyncio
import logging
import os
import platform
import sys

import rich_click as click
from click.core import Context
from rich.logging import RichHandler

from .accounts import run_accounts
from .compile import run_compile
from .console import console
from .detect import run_detect
from .fuzz import run_fuzz
from .init import run_init
from .lsp import run_lsp
from .print import run_print
from .run import run_run
from .svm import run_svm
from .test import run_test

if platform.system() != "Windows":
    try:
        from asyncio import (
            ThreadedChildWatcher,  # pyright: ignore reportGeneralTypeIssues
        )
    except ImportError:
        from woke.utils.threaded_child_watcher import ThreadedChildWatcher


def excepthook(attach: bool, type, value, traceback):
    from rich.console import Console
    from rich.traceback import Traceback

    traceback_console = Console(stderr=True)
    traceback_console.print(
        Traceback.from_exception(
            type,
            value,
            traceback,
            suppress=[click],
        )
    )

    if attach:
        import ipdb

        ipdb.pm()


@click.group()
@click.option(
    "--debug",
    "-d",
    is_flag=True,
    default=False,
    help="Set logging level to debug and attach debugger on exception.",
)
@click.option(
    "--profile", is_flag=True, default=False, help="Enable profiling using cProfile."
)
@click.version_option(message="%(version)s", package_name="woke")
@click.pass_context
def main(ctx: Context, debug: bool, profile: bool) -> None:
    if profile:
        import atexit
        import cProfile

        pr = cProfile.Profile()
        pr.enable()

        def exit():
            pr.disable()
            pr.dump_stats("woke.prof")

        atexit.register(exit)

    logging.basicConfig(
        format="%(asctime)s %(name)s: %(message)s",
        handlers=[RichHandler(show_time=False, console=console)],
        force=True,  # pyright: ignore reportGeneralTypeIssues
    )
    sys.excepthook = lambda type, value, traceback: excepthook(
        debug, type, value, traceback
    )

    if debug:
        from woke.core.logging import set_debug

        set_debug(True)

    ctx.ensure_object(dict)
    ctx.obj["debug"] = debug

    if platform.system() == "Windows":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    else:
        asyncio.get_event_loop_policy().set_child_watcher(
            ThreadedChildWatcher()  # pyright: ignore reportUnboundVariable
        )

    os.environ["PYTHONBREAKPOINT"] = "ipdb.set_trace"


main.add_command(run_accounts)
main.add_command(run_compile)
main.add_command(run_detect)
main.add_command(run_fuzz)
main.add_command(run_init)
main.add_command(run_lsp)
main.add_command(run_print)
main.add_command(run_run)
main.add_command(run_svm)
main.add_command(run_test)


@main.command(name="config")
@click.pass_context
def config(ctx: Context) -> None:
    """Print loaded config options in JSON format."""
    from woke.config import WokeConfig

    config = WokeConfig()
    config.load_configs()
    console.print_json(str(config))


def woke_solc() -> None:
    import subprocess
    import sys

    from woke.config import WokeConfig
    from woke.core.solidity_version import SolidityVersion
    from woke.svm import SolcVersionManager

    logging.basicConfig(level=logging.CRITICAL)
    config = WokeConfig()
    config.load_configs()
    svm = SolcVersionManager(config)

    version_file_path = config.global_data_path / ".woke_solc_version"
    if not version_file_path.is_file():
        console.print(
            "Target solc version is not configured. Run 'woke svm use' or 'woke svm switch' command."
        )
        sys.exit(1)

    version = SolidityVersion.fromstring(version_file_path.read_text())
    solc_path = svm.get_path(version)

    if not svm.installed(version):
        console.print(f"solc version {version} is not installed.")
        sys.exit(1)

    proc = subprocess.run(
        [str(solc_path)] + sys.argv[1:],
        stdin=None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    print(proc.stdout.decode("utf-8"), end="")
    sys.exit(proc.returncode)
