import asyncio
import logging
from pathlib import Path
from typing import Set, Tuple

import click
from click.core import Context
from watchdog.observers import Observer

from woke.compiler.compiler import CompilationFileSystemEventHandler, SolidityCompiler
from woke.compiler.solc_frontend.input_data_model import SolcOutputSelectionEnum
from woke.config import WokeConfig

from ..utils.file_utils import is_relative_to
from .console import console


async def compile(
    config: WokeConfig,
    paths: Tuple[str],
    no_artifacts: bool,
    no_warnings: bool,
    force: bool,
    watch: bool,
):
    compiler = SolidityCompiler(config)

    if watch:
        fs_handler = CompilationFileSystemEventHandler(
            config,
            asyncio.get_event_loop(),
            compiler,
            [SolcOutputSelectionEnum.AST],
            write_artifacts=not no_artifacts,
            console=console,
            no_warnings=no_warnings,
        )

        observer = Observer()
        observer.schedule(
            fs_handler,
            str(config.project_root_path),
            recursive=True,
        )
        observer.start()
    else:
        fs_handler = None
        observer = None

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

    if not force:
        compiler.load(console=console)

    # TODO Allow choosing build artifacts subset in compile subcommand
    await compiler.compile(
        sol_files,
        [SolcOutputSelectionEnum.AST],
        write_artifacts=not no_artifacts,
        force_recompile=force,
        console=console,
        no_warnings=no_warnings,
    )

    if watch:
        assert fs_handler is not None
        assert observer is not None
        try:
            await fs_handler.run()
        except KeyboardInterrupt:
            pass
        finally:
            observer.stop()
            observer.join()


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
@click.option(
    "--watch",
    "-w",
    is_flag=True,
    default=False,
    help="Watch for changes in the project and recompile on change.",
)
@click.pass_context
def run_compile(
    ctx: Context,
    paths: Tuple[str],
    no_artifacts: bool,
    no_warnings: bool,
    force: bool,
    watch: bool,
) -> None:
    """Compile the project."""
    config = WokeConfig(woke_root_path=ctx.obj["woke_root_path"])
    config.load_configs()  # load ~/.woke/config.toml and ./woke.toml

    asyncio.run(compile(config, paths, no_artifacts, no_warnings, force, watch))
