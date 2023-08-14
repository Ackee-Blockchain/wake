from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Set

import rich_click as click
from click.core import Context

if TYPE_CHECKING:
    from woke.config import WokeConfig


def write_config(config: WokeConfig) -> None:
    with config.project_root_path.joinpath("woke.toml").open("w") as f:
        f.write("[compiler.solc]\n")
        f.write('ignore_paths = ["node_modules", ".woke-build", "venv", "lib"]\n')
        f.write('include_paths = ["node_modules"]\n')
        if len(config.compiler.solc.remappings) > 0:
            f.write("remappings = [\n")
            for r in config.compiler.solc.remappings:
                f.write(f'    "{r}",\n')
            f.write("]\n")
        if config.compiler.solc.via_IR:
            f.write("via_IR = true\n")
        f.write("\n")

        if config.compiler.solc.optimizer.enabled:
            f.write("[compiler.solc.optimizer]\n")
            f.write("enabled = true\n")
            f.write(f"runs = {config.compiler.solc.optimizer.runs}\n")
            f.write("\n")

        f.write("[detectors]\n")
        f.write("exclude = []\n")
        f.write('ignore_paths = ["node_modules", ".woke-build", "venv", "lib"]\n')
        f.write("\n")

        f.write("[testing]\n")
        f.write('cmd = "anvil"\n')
        f.write("\n")

        f.write("[testing.anvil]\n")
        f.write(f'cmd_args = "{config.testing.anvil.cmd_args}"\n')
        f.write("\n")

        f.write("[testing.ganache]\n")
        f.write(f'cmd_args = "{config.testing.ganache.cmd_args}"\n')
        f.write("\n")

        f.write("[testing.hardhat]\n")
        f.write(f'cmd_args = "{config.testing.hardhat.cmd_args}"')


def update_gitignore(file: Path) -> None:
    if file.exists():
        lines = file.read_text().splitlines()
    else:
        lines = []

    new_lines = [
        ".woke-build",
        ".woke-logs",
        ".env",
        "pytypes",
        "__pycache__/",
        "*.py[cod]",
        ".hypothesis/",
        "woke-coverage.cov",
    ]

    new_lines = [l for l in new_lines if l not in lines]

    if len(new_lines) > 0:
        with file.open("a") as f:
            f.write("\n" + "\n".join(new_lines))


@click.group(name="init", invoke_without_command=True)
@click.option(
    "--force", "-f", is_flag=True, default=False, help="Force overwrite existing files."
)
@click.pass_context
def run_init(ctx: Context, force: bool):
    """Initialize project."""
    from woke.config import WokeConfig

    config = WokeConfig()
    config.load_configs()
    ctx.obj["config"] = config

    if ctx.invoked_subcommand is None:
        import subprocess

        from ..compiler import SolcOutputSelectionEnum, SolidityCompiler
        from ..compiler.solc_frontend import SolcOutputErrorSeverityEnum
        from ..development.pytypes_generator import TypeGenerator
        from ..utils.file_utils import copy_dir, is_relative_to
        from .console import console

        # create tests directory
        copy_dir(
            Path(__file__).parent.parent / "templates" / "tests",
            config.project_root_path / "tests",
            overwrite=force,
        )

        # create scripts directory
        copy_dir(
            Path(__file__).parent.parent / "templates" / "scripts",
            config.project_root_path / "scripts",
            overwrite=force,
        )

        # update .gitignore, --force is not needed
        update_gitignore(config.project_root_path / ".gitignore")

        # load foundry remappings, if foundry.toml exists
        if (config.project_root_path / "foundry.toml").exists():
            remappings = (
                subprocess.run(["forge", "remappings"], capture_output=True)
                .stdout.decode("utf-8")
                .splitlines()
            )
            config.update({"compiler": {"solc": {"remappings": remappings}}}, [])

        sol_files: Set[Path] = set()
        start = time.perf_counter()
        with console.status("[bold green]Searching for *.sol files...[/]"):
            for file in config.project_root_path.rglob("**/*.sol"):
                if (
                    not any(
                        is_relative_to(file, p)
                        for p in config.compiler.solc.ignore_paths
                    )
                    and file.is_file()
                ):
                    sol_files.add(file)
        end = time.perf_counter()
        console.log(
            f"[green]Found {len(sol_files)} *.sol files in [bold green]{end - start:.2f} s[/bold green][/]"
        )

        if len(sol_files) == 0:
            (config.project_root_path / "contracts").mkdir(exist_ok=True)
        else:
            compiler = SolidityCompiler(config)
            compiler.load(console=console)

            _, errors = asyncio.run(
                compiler.compile(
                    sol_files,
                    [SolcOutputSelectionEnum.ALL],
                    write_artifacts=True,
                    force_recompile=False,
                    console=console,
                    no_warnings=True,
                )
            )

            contract_size_limit = any(
                e
                for e in errors
                if e.severity == SolcOutputErrorSeverityEnum.WARNING
                and "Contract code size" in e.message
            )
            stack_too_deep = any(
                e
                for e in errors
                if e.severity == SolcOutputErrorSeverityEnum.ERROR
                and "Stack too deep" in e.message
            )

            if contract_size_limit or stack_too_deep:
                if stack_too_deep:
                    console.print(
                        "[yellow]Stack too deep error detected. Enabling optimizer.[/]"
                    )
                elif contract_size_limit:
                    console.print(
                        "[yellow]Contract size limit warning detected. Enabling optimizer.[/]"
                    )
                config.update(
                    {"compiler": {"solc": {"optimizer": {"enabled": True}}}}, []
                )

                _, errors = asyncio.run(
                    compiler.compile(
                        sol_files,
                        [SolcOutputSelectionEnum.ALL],
                        write_artifacts=True,
                        force_recompile=False,
                        console=console,
                        no_warnings=True,
                    )
                )
                stack_too_deep = any(
                    e
                    for e in errors
                    if e.severity == SolcOutputErrorSeverityEnum.ERROR
                    and "Stack too deep" in e.message
                )

                if stack_too_deep:
                    console.print(
                        "[yellow]Stack too deep error still detected. Enabling --via-ir.[/]"
                    )
                    config.update({"compiler": {"solc": {"via_IR": True}}}, [])

                    _, errors = asyncio.run(
                        compiler.compile(
                            sol_files,
                            [SolcOutputSelectionEnum.ALL],
                            write_artifacts=True,
                            force_recompile=False,
                            console=console,
                            no_warnings=True,
                        )
                    )
            start = time.perf_counter()
            with console.status("[bold green]Generating pytypes..."):
                type_generator = TypeGenerator(config, False)
                type_generator.generate_types(compiler)
            end = time.perf_counter()
            console.log(
                f"[green]Generated pytypes in [bold green]{end - start:.2f} s[/]"
            )

    if not (config.project_root_path / "woke.toml").exists() or force:
        write_config(config)


async def run_init_pytypes(
    config: WokeConfig, return_tx: bool, warnings: bool, watch: bool
):
    from watchdog.observers import Observer

    from ..compiler import SolcOutputSelectionEnum, SolidityCompiler
    from ..compiler.build_data_model import ProjectBuild, ProjectBuildInfo
    from ..compiler.compiler import CompilationFileSystemEventHandler
    from ..compiler.solc_frontend import SolcOutputErrorSeverityEnum
    from ..development.pytypes_generator import TypeGenerator
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

    sol_files: Set[Path] = set()
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

    if watch:
        fs_handler = CompilationFileSystemEventHandler(
            config,
            sol_files,
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
    help="Return transaction objects from deploy functions instead of contract instances",
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
    """Generate Python types from Solidity sources."""
    config: WokeConfig = ctx.obj["config"]
    asyncio.run(run_init_pytypes(config, return_tx, warnings, watch))


@run_init.command(name="detector")
@click.argument("detector_name", type=str)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    default=False,
    help="Force overwrite existing detector.",
)
@click.pass_context
def init_detector(ctx: Context, detector_name: str, force: bool) -> None:
    from woke.detectors.template import TEMPLATE

    config: WokeConfig = ctx.obj["config"]

    module_name = detector_name.replace("-", "_")

    if not module_name.isidentifier():
        raise click.BadParameter(
            f"Detector name must be a valid Python identifier, got {detector_name}"
        )

    class_name = "".join([s.capitalize() for s in module_name.split("_") if s != ""])
    dir_path = config.project_root_path / "detectors"
    init_path = dir_path / "__init__.py"
    detector_path = dir_path / f"{module_name}.py"

    if detector_path.exists() and not force:
        raise click.ClickException(
            f"Detector {detector_name} already exists. Use --force to overwrite."
        )

    if not dir_path.exists():
        dir_path.mkdir()

    detector_path.write_text(
        TEMPLATE.format(class_name=class_name, command_name=detector_name)
    )

    if not init_path.exists():
        init_path.touch()

    import_str = f"from .{module_name} import {class_name}"
    if import_str not in init_path.read_text().splitlines():
        with init_path.open("a") as f:
            f.write(f"\n{import_str}")


@run_init.command(name="printer")
@click.argument("printer_name", type=str)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    default=False,
    help="Force overwrite existing printer.",
)
@click.pass_context
def init_printer(ctx: Context, printer_name: str, force: bool) -> None:
    from woke.printers.template import TEMPLATE

    config: WokeConfig = ctx.obj["config"]

    module_name = printer_name.replace("-", "_")

    if not module_name.isidentifier():
        raise click.BadParameter(
            f"Printer name must be a valid Python identifier, got {printer_name}"
        )

    class_name = "".join([s.capitalize() for s in module_name.split("_") if s != ""])
    dir_path = config.project_root_path / "printers"
    init_path = dir_path / "__init__.py"
    printer_path = dir_path / f"{module_name}.py"

    if printer_path.exists() and not force:
        raise click.ClickException(
            f"Printer {printer_name} already exists. Use --force to overwrite."
        )

    if not dir_path.exists():
        dir_path.mkdir()

    printer_path.write_text(
        TEMPLATE.format(class_name=class_name, command_name=printer_name)
    )

    if not init_path.exists():
        init_path.touch()

    import_str = f"from .{module_name} import {class_name}"
    if import_str not in init_path.read_text().splitlines():
        with init_path.open("a") as f:
            f.write(f"\n{import_str}")
