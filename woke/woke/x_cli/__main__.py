from click.core import Context
import click
import rich.traceback

from woke.a_config import WokeConfig
from .console import console


@click.group()
@click.option("--debug/--no-debug", default=True)
@click.pass_context
def main(ctx: Context, debug: bool) -> None:
    ctx.ensure_object(dict)
    ctx.obj["debug"] = debug

    rich.traceback.install(show_locals=True, suppress=[click], console=console)


@click.group()
def svm_main() -> None:
    rich.traceback.install(show_locals=True, suppress=[click], console=console)


@main.command(name="config")
@click.pass_context
def config(ctx: Context) -> None:
    """Print loaded config options in JSON format."""
    config = WokeConfig()
    config.load_configs()
    console.print_json(str(config))
