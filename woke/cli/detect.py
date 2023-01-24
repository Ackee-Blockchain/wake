import asyncio
import sys
import time
from pathlib import Path
from typing import Set, Tuple

import rich.terminal_theme
import rich_click as click


@click.command(name="detect")
@click.argument("paths", nargs=-1, type=click.Path(exists=True))
@click.option(
    "--svg", is_flag=True, default=False, help="Capture the output as an SVG file."
)
@click.option(
    "--no-artifacts", is_flag=True, default=False, help="Do not write build artifacts."
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Force recompile the project without previous build artifacts.",
)
@click.pass_context
def run_detect(
    ctx: click.Context, paths: Tuple[str], svg: bool, no_artifacts: bool, force: bool
) -> None:
    """Run vulnerability detectors on the project."""

    from ..analysis.detectors.api import detect, print_detection, print_detectors
    from ..compiler import SolcOutputSelectionEnum, SolidityCompiler
    from ..compiler.build_data_model import ProjectBuild
    from ..compiler.solc_frontend import SolcOutputError, SolcOutputErrorSeverityEnum
    from ..config import WokeConfig
    from ..utils.file_utils import is_relative_to
    from .console import console

    config = WokeConfig()
    config.load_configs()  # load ~/.woke/config.toml and ./woke.toml

    sol_files: Set[Path] = set()
    start = time.perf_counter()
    with console.status("[bold green]Searching for *.sol files...[/]"):
        if len(paths) == 0:
            for file in config.project_root_path.rglob("**/*.sol"):
                if (
                    not any(
                        is_relative_to(file, p)
                        for p in config.compiler.solc.ignore_paths
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
    end = time.perf_counter()
    console.log(
        f"[green]Found {len(sol_files)} *.sol files in [bold green]{end - start:.2f} s[/bold green][/]"
    )

    compiler = SolidityCompiler(config)

    if not force:
        compiler.load(console=console)

    build: ProjectBuild
    errors: Set[SolcOutputError]
    build, errors = asyncio.run(
        compiler.compile(
            sol_files,
            [SolcOutputSelectionEnum.ALL],
            write_artifacts=not no_artifacts,
            force_recompile=force,
            console=console,
        )
    )

    errored = any(
        error.severity == SolcOutputErrorSeverityEnum.ERROR for error in errors
    )
    if errored:
        sys.exit(1)

    console.record = True

    if svg:
        print_detectors(config, theme="vs")
    else:
        print_detectors(config)

    for detection in detect(config, build.source_units, console=console):
        if svg:
            print_detection(detection, theme="vs")
        else:
            print_detection(detection)

    if svg:
        console.save_svg(
            "woke-detections.svg",
            title="Woke",
            theme=rich.terminal_theme.DEFAULT_TERMINAL_THEME,
        )
