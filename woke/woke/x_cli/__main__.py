import logging
from pathlib import Path
from typing import Optional

from click.core import Context
from rich.logging import RichHandler
import click
import rich.traceback

from woke.a_config import WokeConfig
from .console import console
from .compile import run_compile


@click.group()
@click.option("--woke-root-path", required=False, type=click.Path(exists=True))
@click.option("--debug/--no-debug", default=False)
@click.pass_context
def main(ctx: Context, woke_root_path: Optional[str], debug: bool) -> None:
    rich.traceback.install(show_locals=debug, suppress=[click], console=console)
    logging.basicConfig(
        format="%(name)s: %(message)s",
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


@click.group()
def svm_main() -> None:
    rich.traceback.install(show_locals=True, suppress=[click], console=console)
    logging.basicConfig(
        format="%(name)s: %(message)s",
        handlers=[RichHandler(show_time=False, console=console)],
    )


@main.command(name="config")
@click.pass_context
def config(ctx: Context) -> None:
    """Print loaded config options in JSON format."""
    config = WokeConfig()
    config.load_configs()
    console.print_json(str(config))
