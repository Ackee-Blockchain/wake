import asyncio
import pathlib
import sys
import time
from typing import Set

import rich_click as click
from click.core import Context

from woke.config import WokeConfig


@click.group(name="init")
@click.pass_context
def run_init(ctx: Context):
    """Create default project skeleton."""
    config = WokeConfig()
    config.load_configs()
    ctx.obj["config"] = config


async def run_init_pytypes(
    config: WokeConfig, return_tx: bool, warnings: bool, watch: bool
):
    from watchdog.observers import Observer

    from ..compiler import SolcOutputSelectionEnum, SolidityCompiler
    from ..compiler.build_data_model import ProjectBuild, ProjectBuildInfo
    from ..compiler.compiler import CompilationFileSystemEventHandler
    from ..compiler.solc_frontend import SolcOutputErrorSeverityEnum
    from ..testing.pytypes_generator import TypeGenerator
    from ..utils.file_utils import is_relative_to
    from .console import console

    def callback(build: ProjectBuild, build_info: ProjectBuildInfo):
        start = time.perf_counter()
        with console.status("[bold green]Generating pytypes..."):
            type_generator = TypeGenerator(config, return_tx)
            type_generator.generate_types(compiler)
        end = time.perf_counter()
        console.log(f"[green]Generated pytypes in [bold green]{end - start:.2f} s[/]")

    compiler = SolidityCompiler(config)

    if watch:
        fs_handler = CompilationFileSystemEventHandler(
            config,
            asyncio.get_event_loop(),
            compiler,
            [SolcOutputSelectionEnum.ALL],
            write_artifacts=True,
            console=console,
            no_warnings=not warnings,
        )
        fs_handler.register_callback(callback)

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

    sol_files: Set[pathlib.Path] = set()
    start = time.perf_counter()
    with console.status("[bold green]Searching for *.sol files...[/]"):
        for file in config.project_root_path.rglob("**/*.sol"):
            if (
                not any(
                    is_relative_to(file, p) for p in config.compiler.solc.ignore_paths
                )
                and file.is_file()
            ):
                sol_files.add(file)
    end = time.perf_counter()
    console.log(
        f"[green]Found {len(sol_files)} *.sol files in [bold green]{end - start:.2f} s[/bold green][/]"
    )

    compiler.load(console=console)

    _, errors = await compiler.compile(
        sol_files,
        [SolcOutputSelectionEnum.ALL],
        write_artifacts=True,
        force_recompile=False,
        console=console,
        no_warnings=not warnings,
    )

    start = time.perf_counter()
    with console.status("[bold green]Generating pytypes..."):
        type_generator = TypeGenerator(config, return_tx)
        type_generator.generate_types(compiler)
    end = time.perf_counter()
    console.log(f"[green]Generated pytypes in [bold green]{end - start:.2f} s[/]")

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
    else:
        errored = any(e.severity == SolcOutputErrorSeverityEnum.ERROR for e in errors)
        if errored:
            sys.exit(1)


@run_init.command(name="pytypes")
@click.option(
    "--return-tx",
    is_flag=True,
    default=False,
    help="Return transaction objects instead of return data by default.",
)
@click.option(
    "--warnings",
    "-W",
    is_flag=True,
    default=False,
    help="Print compilation warnings to console.",
)
@click.option(
    "--watch",
    "-w",
    is_flag=True,
    default=False,
    help="Watch for changes in the project and regenerate pytypes on change.",
)
@click.pass_context
def init_pytypes(ctx: Context, return_tx: bool, warnings: bool, watch: bool) -> None:
    """Generate Python contract types from Solidity ABI."""
    config: WokeConfig = ctx.obj["config"]
    asyncio.run(run_init_pytypes(config, return_tx, warnings, watch))


@run_init.command(name="fuzz")
@click.option(
    "--force",
    "-f",
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
    "-W",
    is_flag=True,
    default=False,
    help="Print compilation warnings to console.",
)
@click.option(
    "--watch",
    "-w",
    is_flag=True,
    default=False,
    help="Watch for changes in the project and regenerate pytypes on change.",
)
@click.pass_context
def init_fuzz(
    ctx: Context, force: bool, return_tx: bool, warnings: bool, watch: bool
) -> None:
    """Generate Python contract types and create example fuzz tests."""

    from ..utils.file_utils import copy_dir

    config: WokeConfig = ctx.obj["config"]

    examples_dir = pathlib.Path(__file__).parent.parent.resolve() / "examples/fuzzer"
    tests_dir = config.project_root_path / "tests"
    copy_dir(examples_dir, tests_dir, overwrite=force)

    asyncio.run(run_init_pytypes(config, return_tx, warnings, watch))
