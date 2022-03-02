import logging

from click.core import Context
from rich.logging import RichHandler
import click
import rich.traceback

from woke.a_config import WokeConfig
from .console import console


@click.group()
@click.option("--debug/--no-debug", default=True)
@click.pass_context
def main(ctx: Context, debug: bool) -> None:
    rich.traceback.install(show_locals=True, suppress=[click], console=console)
    logging.basicConfig(
        format="%(name)s: %(message)s",
        handlers=[RichHandler(show_time=False, console=console)],
    )

    ctx.ensure_object(dict)
    ctx.obj["debug"] = debug


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
