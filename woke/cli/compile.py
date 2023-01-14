import asyncio
from pathlib import Path
from typing import Set, Tuple

import click
from click.core import Context

from woke.compile.compiler import SolidityCompiler
from woke.compile.solc_frontend.input_data_model import SolcOutputSelectionEnum
from woke.config import WokeConfig

from ..compile.build_data_model import BuildInfo
from ..compile.solc_frontend import SolcOutputError
from ..utils.file_utils import is_relative_to
from .console import console


@click.command(name="compile")
@click.argument("paths", nargs=-1, type=click.Path(exists=True))
@click.option(
    "--no-artifacts", is_flag=True, default=False, help="Do not write build artifacts."
)
@click.option(
    "--no-warnings",
    is_flag=True,
    default=False,
    help="Do not print compilation warnings.",
)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    default=False,
    help="Force recompile the project without previous build artifacts.",
)
@click.pass_context
def run_compile(
    ctx: Context, paths: Tuple[str], no_artifacts: bool, no_warnings: bool, force: bool
) -> None:
    """Compile the project."""
    config = WokeConfig(woke_root_path=ctx.obj["woke_root_path"])
    config.load_configs()  # load ~/.woke/config.toml and ./woke.toml

    sol_files: Set[Path] = set()
    if len(paths) == 0:
        for file in config.project_root_path.rglob("**/*.sol"):
            if (
                not any(
                    is_relative_to(file, p) for p in config.compiler.solc.ignore_paths
                )
                and file.is_file()
            ):
                sol_files.add(file)
    else:
        for p in paths:
            path = Path(p)
            if path.is_file():
                if not path.match("*.sol"):
                    raise ValueError(f"Argument `{p}` is not a Solidity file.")
                sol_files.add(path)
            elif path.is_dir():
                for file in path.rglob("**/*.sol"):
                    if (
                        not any(
                            is_relative_to(file, p)
                            for p in config.compiler.solc.ignore_paths
                        )
                        and file.is_file()
                    ):
                        sol_files.add(file)
            else:
                raise ValueError(f"Argument `{p}` is not a file or directory.")

    compiler = SolidityCompiler(config)

    if not force:
        try:
            compiler.load()
        except Exception:
            pass

    # TODO Allow choosing build artifacts subset in compile subcommand
    build: BuildInfo
    errors: Set[SolcOutputError]
    build, errors = asyncio.run(
        compiler.compile(
            sol_files,
            [SolcOutputSelectionEnum.AST],
            write_artifacts=not no_artifacts,
            force_recompile=force,
            console=console,
            no_warnings=no_warnings,
        )
    )
