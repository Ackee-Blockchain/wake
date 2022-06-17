import click
from click.core import Context

from woke.config import WokeConfig
from woke.fuzzer.abi_to_type import generate_types


@click.group(name="init")
@click.pass_context
def run_init(ctx: Context):
    """Create default project skeleton."""
    config = WokeConfig(woke_root_path=ctx.obj["woke_root_path"])
    config.load_configs()
    ctx.obj["config"] = config


@run_init.command(name="types")
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Overwrite existing types.",
)
@click.pass_context
def init_types(ctx: Context, force: bool) -> None:
    """Generate Python contract types from Solidity ABI."""
    config: WokeConfig = ctx.obj["config"]
    generate_types(config, force)
