from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Set, Tuple

import rich_click as click
from click.core import Context

from wake.core.enums import EvmVersionEnum

if TYPE_CHECKING:
    from wake.config import WakeConfig


async def compile(
    config: WakeConfig,
    paths: Tuple[str],
    no_artifacts: bool,
    no_warnings: bool,
    force: bool,
    watch: bool,
    incremental: Optional[bool],
):
    from watchdog.observers import Observer

    from wake.compiler.compiler import (
        CompilationFileSystemEventHandler,
        SolidityCompiler,
    )
    from wake.compiler.solc_frontend.input_data_model import SolcOutputSelectionEnum

    from ..compiler.solc_frontend import SolcOutputErrorSeverityEnum
    from ..utils.file_utils import is_relative_to
    from .console import console

    compiler = SolidityCompiler(config)

    sol_files: Set[Path] = set()
    start = time.perf_counter()
    with console.status("[bold green]Searching for *.sol files...[/]"):
        if len(paths) == 0:
            for file in config.project_root_path.rglob("**/*.sol"):
                if (
                    not any(
                        is_relative_to(file, p)
                        for p in config.compiler.solc.exclude_paths
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
                                for p in config.compiler.solc.exclude_paths
                            )
                            and file.is_file()
                        ):
                            sol_files.add(file)
                else:
                    raise ValueError(f"Argument `{p}` is not a file or directory.")
    end = time.perf_counter()
    console.log(
        f"[green]Found {len(sol_files)} *.sol files in [bold green]{end - start:.2f} s[/bold green][/]"
    )

    if watch:
        fs_handler = CompilationFileSystemEventHandler(
            config,
            sol_files,
            asyncio.get_event_loop(),
            compiler,
            [SolcOutputSelectionEnum.ALL],
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

    if not force:
        compiler.load(console=console)

    # TODO Allow choosing build artifacts subset in compile subcommand
    _, errors = await compiler.compile(
        sol_files,
        [SolcOutputSelectionEnum.ALL],
        write_artifacts=not no_artifacts,
        force_recompile=force,
        console=console,
        no_warnings=no_warnings,
        incremental=incremental,
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
    else:
        errored = any(
            error.severity == SolcOutputErrorSeverityEnum.ERROR for error in errors
        )
        if errored:
            sys.exit(2)


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
@click.option(
    "--incremental/--no-incremental",
    is_flag=True,
    required=False,
    default=None,
    help="Enforce incremental or non-incremental compilation.",
)
@click.option(
    "--allow-path",
    "allow_paths",
    multiple=True,
    type=click.Path(),
    help="Additional allowed paths for solc.",
    envvar="WAKE_COMPILE_ALLOW_PATHS",
    show_envvar=True,
)
@click.option(
    "--evm-version",
    type=click.Choice(
        ["auto"] + [v.value for v in EvmVersionEnum], case_sensitive=False
    ),
    help="Version of the EVM to compile for. Use 'auto' to let the solc decide.",
    envvar="WAKE_COMPILE_EVM_VERSION",
    show_envvar=True,
)
@click.option(
    "--exclude-path",
    "exclude_paths",
    multiple=True,
    type=click.Path(),
    help="Paths to exclude from compilation unless imported from non-excluded paths.",
    envvar="WAKE_COMPILE_EXCLUDE_PATHS",
    show_envvar=True,
)
@click.option(
    "--include-path",
    "include_paths",
    multiple=True,
    type=click.Path(),
    help="Additional paths to search for when importing *.sol files.",
    envvar="WAKE_COMPILE_INCLUDE_PATHS",
    show_envvar=True,
)
@click.option(
    "--optimizer-enabled/--no-optimizer-enabled",
    is_flag=True,
    required=False,
    default=None,
    help="Enforce optimizer enabled or disabled.",
    envvar="WAKE_COMPILE_OPTIMIZER_ENABLED",
    show_envvar=True,
)
@click.option(
    "--optimizer-runs",
    type=int,
    help="Number of optimizer runs.",
    envvar="WAKE_COMPILE_OPTIMIZER_RUNS",
    show_envvar=True,
)
@click.option(
    "--remapping",
    "remappings",
    multiple=True,
    type=str,
    help="Remappings for solc.",
    envvar="WAKE_COMPILE_REMAPPINGS",
    show_envvar=True,
)
@click.option(
    "--target-version",
    type=str,
    help="Target version of solc used to compile. Use 'auto' to automatically select.",
    envvar="WAKE_COMPILE_TARGET_VERSION",
    show_envvar=True,
)
@click.option(
    "--via-ir/--no-via-ir",
    is_flag=True,
    required=False,
    default=None,
    help="Enforce compilation via IR or not.",
    envvar="WAKE_COMPILE_VIA_IR",
    show_envvar=True,
)
@click.pass_context
def run_compile(
    ctx: Context,
    paths: Tuple[str],
    no_artifacts: bool,
    no_warnings: bool,
    force: bool,
    watch: bool,
    incremental: Optional[bool],
    allow_paths: Tuple[str],
    evm_version: Optional[str],
    exclude_paths: Tuple[str],
    include_paths: Tuple[str],
    optimizer_enabled: Optional[bool],
    optimizer_runs: Optional[int],
    remappings: Tuple[str],
    target_version: Optional[str],
    via_ir: Optional[bool],
) -> None:
    """Compile the project."""
    from wake.config import WakeConfig

    config = WakeConfig(local_config_path=ctx.obj.get("local_config_path", None))
    config.load_configs()

    new_options = {}
    deleted_options = []

    if allow_paths:
        new_options["allow_paths"] = allow_paths
    if evm_version is not None:
        if evm_version == "auto":
            deleted_options.append(("compiler", "solc", "evm_version"))
        else:
            new_options["evm_version"] = evm_version
    if exclude_paths:
        new_options["exclude_paths"] = exclude_paths
    if include_paths:
        new_options["include_paths"] = include_paths
    if optimizer_enabled is not None:
        if "optimizer" not in new_options:
            new_options["optimizer"] = {}
        new_options["optimizer"]["enabled"] = optimizer_enabled
    if optimizer_runs is not None:
        if "optimizer" not in new_options:
            new_options["optimizer"] = {}
        new_options["optimizer"]["runs"] = optimizer_runs
    if remappings:
        new_options["remappings"] = remappings
    if target_version is not None:
        if target_version == "auto":
            deleted_options.append(("compiler", "solc", "target_version"))
        else:
            new_options["target_version"] = target_version
    if via_ir is not None:
        new_options["via_IR"] = via_ir

    config.update({"compiler": {"solc": new_options}}, deleted_options)

    asyncio.run(
        compile(config, paths, no_artifacts, no_warnings, force, watch, incremental)
    )
