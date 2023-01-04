import pathlib

import click
from click.core import Context

from woke.config import WokeConfig
from woke.utils import file_utils

from ..testing.pytypes_generator import TypeGenerator


@click.group(name="init")
@click.pass_context
def run_init(ctx: Context):
    """Create default project skeleton."""
    config = WokeConfig(woke_root_path=ctx.obj["woke_root_path"])
    config.load_configs()
    ctx.obj["config"] = config


@run_init.command(name="pytypes")
@click.option(
    "--return-tx",
    is_flag=True,
    default=False,
    help="Return transaction objects instead of return data by default.",
)
@click.option(
    "--warnings",
    "-w",
    is_flag=True,
    default=False,
    help="Print compilation warnings to console.",
)
@click.pass_context
def init_pytypes(ctx: Context, return_tx: bool, warnings: bool) -> None:
    """Generate Python contract types from Solidity ABI."""
    config: WokeConfig = ctx.obj["config"]
    type_generator = TypeGenerator(config, return_tx)
    type_generator.generate_types(warnings)


@run_init.command(name="fuzz")
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Overwrite existing pytypes and tests directories",
)
@click.option(
    "--return-tx",
    is_flag=True,
    default=False,
    help="Return transaction objects instead of return data by default.",
)
@click.option(
    "--warnings",
    "-w",
    is_flag=True,
    default=False,
    help="Print compilation warnings to console.",
)
@click.pass_context
def init_fuzz(ctx: Context, force: bool, return_tx: bool, warnings: bool) -> None:
    """Generate Python contract types and create example fuzz tests."""
    config: WokeConfig = ctx.obj["config"]
    type_generator = TypeGenerator(config, return_tx)
    type_generator.generate_types(warnings)

    examples_dir = pathlib.Path(__file__).parent.parent.resolve() / "examples/fuzzer"
    tests_dir = config.project_root_path / "tests"
    file_utils.copy_dir(examples_dir, tests_dir, overwrite=force)
