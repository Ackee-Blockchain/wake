from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path, PurePath
from typing import TYPE_CHECKING, Iterable, Optional, Set, Tuple

import rich_click as click
from click.core import Context

from ..core.enums import EvmVersionEnum
from .console import console
from .detect import DetectCli, run_detect
from .print import PrintCli, run_print

if TYPE_CHECKING:
    from wake.compiler import SolidityCompiler
    from wake.compiler.build_data_model import SolcOutputError
    from wake.config import WakeConfig


def paths_to_str(paths: Iterable[PurePath], config: WakeConfig) -> str:
    from wake.utils import is_relative_to

    return ", ".join(
        (
            f'"{p.relative_to(config.local_config_path.parent)}"'
            if is_relative_to(p, config.local_config_path.parent)
            else f'"{p}"'
        )
        for p in paths
    )


def write_config(config: WakeConfig) -> None:
    config.local_config_path.parent.mkdir(exist_ok=True, parents=True)
    with config.local_config_path.open("w") as f:
        f.write("[compiler.solc]\n")
        if len(config.compiler.solc.allow_paths) > 0:
            f.write(
                f"allow_paths = [{paths_to_str(config.compiler.solc.allow_paths, config)}]\n"
            )

        if len(config.compiler.solc.exclude_paths) > 0:
            f.write(
                f"exclude_paths = [{paths_to_str(config.compiler.solc.exclude_paths, config)}]\n"
            )

        if len(config.compiler.solc.include_paths) > 0:
            f.write(
                f"include_paths = [{paths_to_str(config.compiler.solc.include_paths, config)}]\n"
            )

        if len(config.compiler.solc.remappings) > 0:
            f.write("remappings = [\n")
            for r in config.compiler.solc.remappings:
                f.write(f'    "{r}",\n')
            f.write("]\n")

        if config.compiler.solc.evm_version is not None:
            f.write(f'evm_version = "{config.compiler.solc.evm_version}"\n')

        if config.compiler.solc.via_IR is not None:
            f.write(f"via_IR = {str(config.compiler.solc.via_IR).lower()}\n")

        if config.compiler.solc.target_version is not None:
            f.write(f'target_version = "{config.compiler.solc.target_version}"\n')

        f.write("\n")

        f.write("[compiler.solc.optimizer]\n")
        if config.compiler.solc.optimizer.enabled is not None:
            f.write(
                f"enabled = {str(config.compiler.solc.optimizer.enabled).lower()}\n"
            )
        f.write(f"runs = {config.compiler.solc.optimizer.runs}\n")
        f.write("\n")

        if (
            config.compiler.solc.metadata.append_CBOR is not None
            or config.compiler.solc.metadata.use_literal_content is not None
            or config.compiler.solc.metadata.bytecode_hash is not None
        ):
            f.write("[compiler.solc.metadata]\n")
            if config.compiler.solc.metadata.append_CBOR is not None:
                f.write(
                    f"append_CBOR = {str(config.compiler.solc.metadata.append_CBOR).lower()}\n"
                )
            if config.compiler.solc.metadata.use_literal_content is not None:
                f.write(
                    f"use_literal_content = {str(config.compiler.solc.metadata.use_literal_content).lower()}\n"
                )
            if config.compiler.solc.metadata.bytecode_hash is not None:
                f.write(
                    f'bytecode_hash = "{config.compiler.solc.metadata.bytecode_hash}"\n'
                )
            f.write("\n")

        if any(
            v is not None
            for v in (
                config.compiler.solc.optimizer.details.peephole,
                config.compiler.solc.optimizer.details.inliner,
                config.compiler.solc.optimizer.details.jumpdest_remover,
                config.compiler.solc.optimizer.details.order_literals,
                config.compiler.solc.optimizer.details.deduplicate,
                config.compiler.solc.optimizer.details.cse,
                config.compiler.solc.optimizer.details.constant_optimizer,
                config.compiler.solc.optimizer.details.simple_counter_for_loop_unchecked_increment,
            )
        ):
            f.write("[compiler.solc.optimizer.details]\n")
            if config.compiler.solc.optimizer.details.peephole is not None:
                f.write(
                    f"peephole = {str(config.compiler.solc.optimizer.details.peephole).lower()}\n"
                )
            if config.compiler.solc.optimizer.details.inliner is not None:
                f.write(
                    f"inliner = {str(config.compiler.solc.optimizer.details.inliner).lower()}\n"
                )
            if config.compiler.solc.optimizer.details.jumpdest_remover is not None:
                f.write(
                    f"jumpdest_remover = {str(config.compiler.solc.optimizer.details.jumpdest_remover).lower()}\n"
                )
            if config.compiler.solc.optimizer.details.order_literals is not None:
                f.write(
                    f"order_literals = {str(config.compiler.solc.optimizer.details.order_literals).lower()}\n"
                )
            if config.compiler.solc.optimizer.details.deduplicate is not None:
                f.write(
                    f"deduplicate = {str(config.compiler.solc.optimizer.details.deduplicate).lower()}\n"
                )
            if config.compiler.solc.optimizer.details.cse is not None:
                f.write(
                    f"cse = {str(config.compiler.solc.optimizer.details.cse).lower()}\n"
                )
            if config.compiler.solc.optimizer.details.constant_optimizer is not None:
                f.write(
                    f"constant_optimizer = {str(config.compiler.solc.optimizer.details.constant_optimizer).lower()}\n"
                )
            if (
                config.compiler.solc.optimizer.details.simple_counter_for_loop_unchecked_increment
                is not None
            ):
                f.write(
                    f"simple_counter_for_loop_unchecked_increment = {str(config.compiler.solc.optimizer.details.simple_counter_for_loop_unchecked_increment).lower()}\n"
                )
            f.write("\n")

        if (
            config.compiler.solc.optimizer.details.yul_details.stack_allocation
            is not None
            or config.compiler.solc.optimizer.details.yul_details.optimizer_steps
            is not None
        ):
            f.write("[compiler.solc.optimizer.details.yul_details]\n")
            if (
                config.compiler.solc.optimizer.details.yul_details.stack_allocation
                is not None
            ):
                f.write(
                    f"stack_allocation = {str(config.compiler.solc.optimizer.details.yul_details.stack_allocation).lower()}\n"
                )
            if (
                config.compiler.solc.optimizer.details.yul_details.optimizer_steps
                is not None
            ):
                f.write(
                    f'optimizer_steps = "{config.compiler.solc.optimizer.details.yul_details.optimizer_steps}"\n'
                )
            f.write("\n")

        f.write("[detectors]\n")
        f.write("exclude = []\n")

        if len(config.detectors.ignore_paths) > 0:
            f.write(
                f"ignore_paths = [{paths_to_str(config.detectors.ignore_paths, config)}]\n"
            )

        if len(config.compiler.solc.exclude_paths) > 0:
            f.write(
                f"exclude_paths = [{paths_to_str(config.compiler.solc.exclude_paths, config)}]\n"
            )

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


def import_foundry_profile(
    config: WakeConfig,
    config_toml: str,
    foundry_toml: str,
    foundry_profile: Optional[str],
) -> None:
    import tomli

    if foundry_profile is None:
        foundry_profile = "default"

    parsed_config = tomli.loads(config_toml)  # output of `forge config`
    parsed_foundry = tomli.loads(foundry_toml)  # contents of `foundry.toml`

    if (
        foundry_profile not in parsed_config["profile"]
        or foundry_profile not in parsed_foundry["profile"]
    ):
        raise ValueError(f"Profile {foundry_profile} not found in foundry.toml")

    c = parsed_config["profile"][foundry_profile]

    if "test" in c:
        config.update(
            {
                "compiler": {
                    "solc": {
                        "exclude_paths": config.compiler.solc.exclude_paths.union(
                            {Path(c["test"])}
                        )
                    }
                }
            },
            [],
        )
        config.update(
            {
                "detectors": {
                    "ignore_paths": config.detectors.ignore_paths.union(
                        {Path(c["test"])}
                    )
                }
            },
            [],
        )

    if "script" in c:
        config.update(
            {
                "compiler": {
                    "solc": {
                        "exclude_paths": config.compiler.solc.exclude_paths.union(
                            {Path(c["script"])}
                        )
                    }
                }
            },
            [],
        )
        config.update(
            {
                "detectors": {
                    "exclude_paths": config.detectors.ignore_paths.union(
                        {Path(c["script"])}
                    )
                }
            },
            [],
        )

    if "remappings" in c:
        config.update({"compiler": {"solc": {"remappings": c["remappings"]}}}, [])

    if "allow_paths" in c:
        config.update({"compiler": {"solc": {"allow_paths": c["allow_paths"]}}}, [])

    if "include_paths" in c:
        config.update({"compiler": {"solc": {"include_paths": c["include_paths"]}}}, [])

    if "evm_version" in parsed_foundry["profile"][foundry_profile]:
        # the value of `evm_version` cannot be trusted in `forge config`
        # using the parsed `foundry.toml` instead
        config.update(
            {
                "compiler": {
                    "solc": {
                        "evm_version": parsed_foundry["profile"][foundry_profile][
                            "evm_version"
                        ]
                    }
                }
            },
            [],
        )

    if "optimizer" in c:
        config.update(
            {"compiler": {"solc": {"optimizer": {"enabled": c["optimizer"]}}}}, []
        )

    if "optimizer_runs" in c:
        config.update(
            {"compiler": {"solc": {"optimizer": {"runs": c["optimizer_runs"]}}}}, []
        )

    if "via_ir" in c:
        config.update({"compiler": {"solc": {"via_IR": c["via_ir"]}}}, [])

    if "solc" in c:
        config.update({"compiler": {"solc": {"target_version": c["solc"]}}}, [])

    if "bytecode_hash" in c:
        config.update(
            {"compiler": {"solc": {"metadata": {"bytecode_hash": c["bytecode_hash"]}}}},
            [],
        )

    if "use_literal_content" in c:
        config.update(
            {
                "compiler": {
                    "solc": {
                        "metadata": {"use_literal_content": c["use_literal_content"]}
                    }
                }
            },
            [],
        )

    if "cbor_metadata" in c:
        config.update(
            {"compiler": {"solc": {"metadata": {"append_CBOR": c["cbor_metadata"]}}}},
            [],
        )

    if "optimizer_details" not in c:
        return

    c = c["optimizer_details"]

    if "peephole" in c:
        config.update(
            {
                "compiler": {
                    "solc": {"optimizer": {"details": {"peephole": c["peephole"]}}}
                },
            },
            [],
        )

    if "inliner" in c:
        config.update(
            {
                "compiler": {
                    "solc": {"optimizer": {"details": {"inliner": c["inliner"]}}}
                },
            },
            [],
        )

    if "jumpdestRemover" in c:
        config.update(
            {
                "compiler": {
                    "solc": {
                        "optimizer": {
                            "details": {"jumpdest_remover": c["jumpdestRemover"]}
                        }
                    }
                },
            },
            [],
        )

    if "orderLiterals" in c:
        config.update(
            {
                "compiler": {
                    "solc": {
                        "optimizer": {"details": {"order_literals": c["orderLiterals"]}}
                    }
                },
            },
            [],
        )

    if "deduplicate" in c:
        config.update(
            {
                "compiler": {
                    "solc": {
                        "optimizer": {"details": {"deduplicate": c["deduplicate"]}}
                    }
                },
            },
            [],
        )

    if "cse" in c:
        config.update(
            {
                "compiler": {"solc": {"optimizer": {"details": {"cse": c["cse"]}}}},
            },
            [],
        )

    if "constantOptimizer" in c:
        config.update(
            {
                "compiler": {
                    "solc": {
                        "optimizer": {
                            "details": {"constant_optimizer": c["constantOptimizer"]}
                        }
                    }
                },
            },
            [],
        )

    if "simpleCounterForLoopUncheckedIncrement" in c:
        config.update(
            {
                "compiler": {
                    "solc": {
                        "optimizer": {
                            "details": {
                                "simple_counter_for_loop_unchecked_increment": c[
                                    "simpleCounterForLoopUncheckedIncrement"
                                ]
                            }
                        }
                    }
                },
            },
            [],
        )

    if "yulDetails" not in c:
        return

    c = c["yulDetails"]

    if "stackAllocation" in c:
        config.update(
            {
                "compiler": {
                    "solc": {
                        "optimizer": {
                            "details": {
                                "yul_details": {
                                    "stack_allocation": c["stackAllocation"]
                                }
                            }
                        }
                    }
                },
            },
            [],
        )

    if "optimizerSteps" in c:
        config.update(
            {
                "compiler": {
                    "solc": {
                        "optimizer": {
                            "details": {
                                "yul_details": {"optimizer_steps": c["optimizerSteps"]}
                            }
                        }
                    }
                },
            },
            [],
        )


def update_gitignore(file: Path) -> None:
    if file.exists():
        lines = file.read_text().splitlines()
    else:
        lines = []

    new_lines = [
        ".wake",
        ".env",
        "pytypes",
        "__pycache__/",
        "*.py[cod]",
        ".hypothesis/",
        "wake-coverage.cov",
    ]

    new_lines = [l for l in new_lines if l not in lines]

    if len(new_lines) > 0:
        with file.open("a") as f:
            f.write("\n" + "\n".join(new_lines))


def update_compilation_config(
    config: WakeConfig,
    compiler: SolidityCompiler,
    errors: Set[SolcOutputError],
    sol_files: Set[Path],
    incremental: Optional[bool],
) -> None:
    from ..compiler import SolcOutputSelectionEnum
    from ..compiler.solc_frontend import SolcOutputErrorSeverityEnum

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
        config.update({"compiler": {"solc": {"optimizer": {"enabled": True}}}}, [])

        _, errors = asyncio.run(
            compiler.compile(
                sol_files,
                [SolcOutputSelectionEnum.ALL],
                write_artifacts=True,
                force_recompile=False,
                console=console,
                no_warnings=True,
                incremental=incremental,
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
                    incremental=incremental,
                )
            )


@click.group(name="up", invoke_without_command=True)
@click.option(
    "--force", "-f", is_flag=True, default=False, help="Force overwrite existing files."
)
@click.option(
    "--incremental/--no-incremental",
    is_flag=True,
    required=False,
    default=None,
    help="Enforce incremental or non-incremental compilation.",
)
@click.option(
    "--example",
    type=click.Choice(["counter"], case_sensitive=False),
    help="Initialize example project.",
)
@click.option(
    "--foundry-profile",
    type=str,
    help="Foundry profile to import.",
)
@click.pass_context
def run_init(
    ctx: Context,
    force: bool,
    incremental: Optional[bool],
    example: Optional[str],
    foundry_profile: Optional[str],
):
    """Initialize project."""
    from wake.config import WakeConfig

    config = WakeConfig(local_config_path=ctx.obj.get("local_config_path", None))
    config.load_configs()
    ctx.obj["config"] = config

    if ctx.invoked_subcommand is not None:
        return

    import glob
    import subprocess

    from ..compiler import SolcOutputSelectionEnum, SolidityCompiler
    from ..compiler.solc_frontend import SolcOutputErrorSeverityEnum
    from ..development.pytypes_generator import TypeGenerator
    from ..utils.file_utils import copy_dir, is_relative_to

    if example is None:
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
    else:
        if any(config.project_root_path.iterdir()) and not force:
            raise click.ClickException(
                f"Project directory {config.project_root_path} is not empty. Use --force to force overwrite."
            )

        copy_dir(
            Path(__file__).parent.parent.parent / "examples" / "counter",
            config.project_root_path,
            overwrite=force,
        )

        subprocess.run(["npm", "install"])

    # update .gitignore, --force is not needed
    update_gitignore(config.project_root_path / ".gitignore")

    # load foundry config, if foundry.toml exists
    if (config.project_root_path / "foundry.toml").exists():
        config_toml = subprocess.run(
            ["forge", "config"], capture_output=True
        ).stdout.decode("utf-8")
        foundry_toml = (config.project_root_path / "foundry.toml").read_text()
        import_foundry_profile(config, config_toml, foundry_toml, foundry_profile)

    sol_files: Set[Path] = set()
    start = time.perf_counter()
    with console.status("[bold green]Searching for *.sol files...[/]"):
        for f in glob.iglob(str(config.project_root_path / "**/*.sol"), recursive=True):
            file = Path(f)
            if (
                not any(
                    is_relative_to(file, p) for p in config.compiler.solc.exclude_paths
                )
                and file.is_file()
            ):
                sol_files.add(file)
        for file in Path(config.wake_contracts_path).rglob("**/*.sol"):
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
                incremental=incremental,
            )
        )

        if not (config.project_root_path / "foundry.toml").exists():
            # check contract size limit & stack too deep and update accordingly
            update_compilation_config(config, compiler, errors, sol_files, incremental)

        start = time.perf_counter()
        with console.status("[bold green]Generating pytypes..."):
            type_generator = TypeGenerator(config, False)
            type_generator.generate_types(compiler)
        end = time.perf_counter()
        console.log(f"[green]Generated pytypes in [bold green]{end - start:.2f} s[/]")

    if not config.local_config_path.exists() or force:
        write_config(config)


@run_init.command(name="gitignore")
@click.pass_context
def run_init_gitignore(ctx: Context) -> None:
    """Initialize .gitignore file."""
    config: WakeConfig = ctx.obj["config"]

    # update .gitignore, --force is not needed
    update_gitignore(config.project_root_path / ".gitignore")


async def run_init_pytypes(
    config: WakeConfig,
    paths: Tuple[str, ...],
    return_tx: bool,
    warnings: bool,
    watch: bool,
    incremental: Optional[bool],
):
    import glob

    from watchdog.observers import Observer

    from ..compiler import SolcOutputSelectionEnum, SolidityCompiler
    from ..compiler.build_data_model import ProjectBuild, ProjectBuildInfo
    from ..compiler.compiler import CompilationFileSystemEventHandler
    from ..compiler.solc_frontend import SolcOutputErrorSeverityEnum
    from ..development.pytypes_generator import TypeGenerator
    from ..utils.file_utils import is_relative_to

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
        if len(paths) == 0:
            for f in glob.iglob(
                str(config.project_root_path / "**/*.sol"), recursive=True
            ):
                file = Path(f)
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
                    for f in glob.iglob(str(path / "**/*.sol"), recursive=True):
                        file = Path(f)
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

        for file in Path(config.wake_contracts_path).rglob("**/*.sol"):
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
        incremental=incremental,
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
            sys.exit(2)


@run_init.command(name="pytypes")
@click.argument("paths", nargs=-1, type=click.Path(exists=True))
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
def init_pytypes(
    ctx: Context,
    paths: Tuple[str, ...],
    return_tx: bool,
    warnings: bool,
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
    """Generate Python types from Solidity sources."""
    config: WakeConfig = ctx.obj["config"]

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
        run_init_pytypes(config, paths, return_tx, warnings, watch, incremental)
    )


@run_init.command(name="config")
@click.option(
    "--force",
    "-f",
    is_flag=True,
    default=False,
    help="Force overwrite existing config file.",
)
@click.option(
    "--incremental/--no-incremental",
    is_flag=True,
    required=False,
    default=None,
    help="Enforce incremental or non-incremental compilation.",
)
@click.option(
    "--foundry-profile",
    type=str,
    help="Foundry profile to import.",
)
@click.pass_context
def run_init_config(
    ctx: Context,
    force: bool,
    incremental: Optional[bool],
    foundry_profile: Optional[str],
):
    """Initialize project config file."""
    import glob
    import subprocess

    from ..compiler import SolcOutputSelectionEnum, SolidityCompiler
    from ..utils.file_utils import is_relative_to

    config: WakeConfig = ctx.obj["config"]

    if config.local_config_path.exists() and not force:
        raise click.ClickException(
            "Config file already exists, use --force to overwrite."
        )

    if (config.project_root_path / "foundry.toml").exists():
        config_toml = subprocess.run(
            ["forge", "config"], capture_output=True
        ).stdout.decode("utf-8")
        foundry_toml = (config.project_root_path / "foundry.toml").read_text()
        import_foundry_profile(config, config_toml, foundry_toml, foundry_profile)
        write_config(config)
        return

    sol_files: Set[Path] = set()
    start = time.perf_counter()
    with console.status("[bold green]Searching for *.sol files...[/]"):
        for f in glob.iglob(str(config.project_root_path / "**/*.sol"), recursive=True):
            file = Path(f)
            if (
                not any(
                    is_relative_to(file, p) for p in config.compiler.solc.exclude_paths
                )
                and file.is_file()
            ):
                sol_files.add(file)
    end = time.perf_counter()
    console.log(
        f"[green]Found {len(sol_files)} *.sol files in [bold green]{end - start:.2f} s[/bold green][/]"
    )

    if len(sol_files) > 0:
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
                incremental=incremental,
            )
        )

        # check contract size limit & stack too deep and update accordingly
        update_compilation_config(config, compiler, errors, sol_files, incremental)

    write_config(config)


@run_init.command(name="detector")
@click.argument("detector_name", type=str)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    default=False,
    help="Force overwrite existing detector.",
)
@click.option(
    "--global",
    "-g",
    "global_",
    is_flag=True,
    default=False,
    help="Create detector in global data directory.",
)
@click.option(
    "--path",
    "-p",
    type=click.Path(file_okay=False),
    default=None,
    help="Path where to create the detector. Must not be set if --global is set.",
)
@click.pass_context
def init_detector(
    ctx: Context, detector_name: str, force: bool, global_: bool, path: Optional[str]
) -> None:
    """
    Create a new detector from template.
    """

    async def module_name_error_callback(module_name: str) -> None:
        raise click.BadParameter(
            f"Detector name must be a valid Python identifier, got {detector_name}"
        )

    async def detector_overwrite_callback(path: Path) -> None:
        raise click.ClickException(f"File {path} already exists.")

    async def detector_exists_callback(other: str) -> None:
        if not force:
            raise click.ClickException(
                f"Detector {detector_name} already exists in {other}. Use --force to force create."
            )

    from wake.detectors.api import init_detector

    from .detect import run_detect

    if global_ and path is not None:
        raise click.BadParameter("Cannot set --global and --path at the same time.")

    config: WakeConfig = ctx.obj["config"]

    # dummy call to load all detectors
    run_detect.list_commands(None)  # pyright: ignore reportGeneralTypeIssues
    detector_path: Path = asyncio.run(
        init_detector(
            config,
            detector_name,
            global_,
            module_name_error_callback,
            detector_overwrite_callback,
            detector_exists_callback,
            path=Path(path).resolve() if path is not None else None,
        )
    )

    link = config.general.link_format.format(
        path=detector_path,
        line=1,
        col=1,
    )

    console.print(
        f"[green]Detector '{detector_name}' created at [link={link}]{detector_path}[/link][/green]"
    )


@run_init.command(name="printer")
@click.argument("printer_name", type=str)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    default=False,
    help="Force overwrite existing printer.",
)
@click.option(
    "--global",
    "-g",
    "global_",
    is_flag=True,
    default=False,
    help="Create detector in global data directory.",
)
@click.option(
    "--path",
    "-p",
    type=click.Path(file_okay=False),
    default=None,
    help="Path where to create the printer. Must not be set if --global is set.",
)
@click.pass_context
def init_printer(
    ctx: Context, printer_name: str, force: bool, global_: bool, path: Optional[str]
) -> None:
    """
    Create a new printer from template.
    """

    async def module_name_error_callback(module_name: str) -> None:
        raise click.BadParameter(
            f"Printer name must be a valid Python identifier, got {printer_name}"
        )

    async def printer_overwrite_callback(path: Path) -> None:
        raise click.ClickException(f"File {path} already exists.")

    async def printer_exists_callback(other: str) -> None:
        if not force:
            raise click.ClickException(
                f"Printer {printer_name} already exists in {other}. Use --force to force create."
            )

    from wake.printers.api import init_printer

    from .print import run_print

    if global_ and path is not None:
        raise click.BadParameter("Cannot set --global and --path at the same time.")

    config: WakeConfig = ctx.obj["config"]

    # dummy call to load all printers
    run_print.list_commands(None)  # pyright: ignore reportGeneralTypeIssues
    printer_path: Path = asyncio.run(
        init_printer(
            config,
            printer_name,
            global_,
            module_name_error_callback,
            printer_overwrite_callback,
            printer_exists_callback,
            path=Path(path).resolve() if path is not None else None,
        )
    )

    link = config.general.link_format.format(
        path=printer_path,
        line=1,
        col=1,
    )

    console.print(
        f"[green]Printer '{printer_name}' created at [link={link}]{printer_path}[/link][/green]"
    )
