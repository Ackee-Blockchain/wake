import logging
import subprocess
import sys
from pathlib import Path
from typing import Optional

import click
import rich.traceback
from click.core import Context
from rich.logging import RichHandler

from woke.config import WokeConfig
from woke.core.solidity_version import SolidityVersion
from woke.svm import SolcVersionManager

from .compile import run_compile
from .console import console
from .lsp import run_lsp
from .svm import run_svm

try:
    from .fuzz import run_fuzz
    from .init import run_init

    FUZZER_AVAILABLE = True
except ImportError:
    FUZZER_AVAILABLE = False


@click.group()
@click.option(
    "--woke-root-path",
    required=False,
    type=click.Path(exists=True),
    help="Override Woke root path.",
)
@click.option("--debug/--no-debug", default=False)
@click.version_option(message="%(version)s", package_name="abch-woke")
@click.pass_context
def main(ctx: Context, woke_root_path: Optional[str], debug: bool) -> None:
    rich.traceback.install(show_locals=debug, suppress=[click], console=console)
    logging.basicConfig(
        format="%(asctime)s %(name)s: %(message)s",
        handlers=[RichHandler(show_time=False, console=console)],
        level=(logging.WARNING if not debug else logging.DEBUG),
    )

    if woke_root_path is not None:
        root_path = Path(woke_root_path)
        if not root_path.is_dir():
            raise ValueError("Woke root path is not a directory.")
    else:
        root_path = None

    ctx.ensure_object(dict)
    ctx.obj["debug"] = debug
    ctx.obj["woke_root_path"] = root_path


main.add_command(run_compile)
main.add_command(run_lsp)
main.add_command(run_svm)

if FUZZER_AVAILABLE:
    main.add_command(run_init)  # type: ignore
    main.add_command(run_fuzz)  # type: ignore


@main.command(name="config")
@click.pass_context
def config(ctx: Context) -> None:
    """Print loaded config options in JSON format."""
    config = WokeConfig()
    config.load_configs()
    console.print_json(str(config))


def woke_solc() -> None:
    logging.basicConfig(level=logging.CRITICAL)
    config = WokeConfig()
    config.load_configs()
    svm = SolcVersionManager(config)

    version_file_path = config.woke_root_path / ".woke_solc_version"
    if not version_file_path.is_file():
        console.print(
            "Target solc version is not configured. Run 'woke svm use' or 'woke svm switch' command."
        )
        sys.exit(1)

    version = SolidityVersion.fromstring(version_file_path.read_text())
    solc_path = svm.get_path(version)

    if not solc_path.is_file():
        console.print(f"solc version {version} is not installed.")
        sys.exit(1)

    proc = subprocess.run(
        [str(solc_path)] + sys.argv[1:],
        stdin=None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    print(proc.stdout.decode("utf-8"))
    sys.exit(proc.returncode)
