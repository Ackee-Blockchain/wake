import pathlib

import click
from click.core import Context

from woke.config import WokeConfig
from woke.fuzzer.abi_to_type import generate_types
from woke.utils import file_utils


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


@run_init.command(name="fuzz")
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Overwrite existing pytypes and tests directories",
)
@click.pass_context
def init_fuzz(ctx: Context, force: bool) -> None:
    """Generate Python contract types and create example fuzz tests."""
    config: WokeConfig = ctx.obj["config"]

    generate_types(config, force)

    examples_dir = pathlib.Path(__file__).parent.parent.resolve() / "examples/fuzzer"
    tests_dir = config.project_root_path / "tests"
    file_utils.copy_dir(examples_dir, tests_dir, overwrite=force)
