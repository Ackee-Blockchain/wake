import asyncio
import logging
import os
import platform
import sys
from pathlib import Path
from typing import Any, List, Optional, Sequence

import rich_click as click
from click.core import Context
from rich.logging import RichHandler

from .accounts import run_accounts
from .compile import run_compile
from .console import console
from .detect import run_detect
from .init import run_init
from .lsp import run_lsp
from .open import run_open
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
        from wake.utils.threaded_child_watcher import ThreadedChildWatcher


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


click.rich_click.COMMAND_GROUPS = {
    "wake detect": [
        {
            "name": "Commands",
            "commands": ["all", "list"],
        }
    ],
    "wake print": [
        {
            "name": "Commands",
            "commands": ["list"],
        }
    ],
}


class AliasedGroup(click.RichGroup):
    def get_command(self, ctx: Context, cmd_name: str) -> Optional[click.Command]:
        if cmd_name == "init":
            cmd_name = "up"
        return super().get_command(ctx, cmd_name)

    def list_commands(self, ctx: Context) -> List[str]:
        return sorted(["up"] + super().list_commands(ctx))

    def main(
        self,
        args: Optional[Sequence[str]] = None,
        prog_name: Optional[str] = None,
        complete_var: Optional[str] = None,
        standalone_mode: bool = True,
        windows_expand_args: bool = True,
        **extra: Any,
    ) -> Any:
        if "_WAKE_COMPLETE" in os.environ:
            import warnings

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                return super().main(
                    args=args,
                    prog_name=prog_name,
                    complete_var=complete_var,
                    standalone_mode=standalone_mode,
                    windows_expand_args=windows_expand_args,
                    **extra,
                )
        else:
            return super().main(
                args=args,
                prog_name=prog_name,
                complete_var=complete_var,
                standalone_mode=standalone_mode,
                windows_expand_args=windows_expand_args,
                **extra,
            )


@click.group(cls=AliasedGroup, context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "--debug",
    "-d",
    is_flag=True,
    default=False,
    help="Set logging level to debug and attach debugger on exception.",
)
@click.option(
    "--silent",
    "-s",
    is_flag=True,
    default=False,
    help="Disable all stdout output.",
)
@click.option(
    "--profile", is_flag=True, default=False, help="Enable profiling using cProfile."
)
@click.option(
    "--config",
    required=False,
    type=click.Path(exists=False, dir_okay=False),
    envvar="WAKE_CONFIG",
    help="Path to the local config file.",
)
@click.version_option(message="%(version)s", package_name="eth-wake")
@click.pass_context
def main(
    ctx: Context, debug: bool, silent: bool, profile: bool, config: Optional[str]
) -> None:
    from wake.migrations import run_woke_wake_migration, run_xdg_migration

    if profile:
        import atexit
        import cProfile

        pr = cProfile.Profile()
        pr.enable()

        def exit():
            pr.disable()
            wake_path = Path.cwd() / ".wake"
            wake_path.mkdir(exist_ok=True)
            pr.dump_stats(wake_path / "wake.prof")

        atexit.register(exit)

    logging.basicConfig(
        format="%(asctime)s %(name)s: %(message)s",
        handlers=[RichHandler(show_time=False, console=console, markup=True)],
        force=True,  # pyright: ignore reportGeneralTypeIssues
    )
    sys.excepthook = lambda type, value, traceback: excepthook(
        debug, type, value, traceback
    )

    if debug:
        from wake.core.logging import set_debug

        set_debug(True)

    ctx.ensure_object(dict)
    ctx.obj["debug"] = debug
    ctx.obj["local_config_path"] = config

    if config is not None:
        try:
            Path(config).resolve().relative_to(Path.cwd())
        except ValueError:
            console.print(
                f"[red]Config path must be relative to current directory: {Path.cwd()}[/red]"
            )
            sys.exit(1)

    if platform.system() == "Windows":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    else:
        asyncio.get_event_loop_policy().set_child_watcher(
            ThreadedChildWatcher()  # pyright: ignore reportUnboundVariable
        )

    os.environ["PYTHONBREAKPOINT"] = "ipdb.set_trace"

    if silent:
        from wake.utils.null_file import NullFile

        console.file = NullFile()

    run_xdg_migration()
    run_woke_wake_migration()


main.add_command(run_accounts)
main.add_command(run_compile)
main.add_command(run_detect)
main.add_command(run_init)
main.add_command(run_lsp)
main.add_command(run_open)
main.add_command(run_print)
main.add_command(run_run)
main.add_command(run_svm)
main.add_command(run_test)


@main.command(name="config")
@click.pass_context
def config(ctx: Context) -> None:
    """Print loaded config options in JSON format."""
    from wake.config import WakeConfig

    config = WakeConfig(local_config_path=ctx.obj.get("local_config_path", None))
    config.load_configs()
    console.print_json(str(config))


def wake_solc() -> None:
    import subprocess
    import sys

    from wake.config import WakeConfig
    from wake.core.solidity_version import SolidityVersion
    from wake.migrations import run_woke_wake_migration, run_xdg_migration
    from wake.svm import SolcVersionManager

    logging.basicConfig(level=logging.CRITICAL)

    run_xdg_migration()
    run_woke_wake_migration()

    # WARNING: this config instance does not accept local config path
    config = WakeConfig()
    config.load_configs()
    svm = SolcVersionManager(config)

    version_file_path = config.global_data_path / "solc-version.txt"
    if not version_file_path.is_file():
        console.print(
            "Target solc version is not configured. Run 'wake svm use' or 'wake svm switch' command."
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
