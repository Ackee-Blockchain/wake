import asyncio
from typing import Tuple

import click
from click import Context
from rich.progress import Progress

from woke.config import WokeConfig
from woke.core.solidity_version import SolidityVersion, SolidityVersionExpr
from woke.svm import SolcVersionManager

from .console import console


@click.group(name="svm")
@click.pass_context
def run_svm(ctx: Context):
    """Run Woke solc version manager."""
    config = WokeConfig(woke_root_path=ctx.obj["woke_root_path"])
    config.load_configs()
    ctx.obj["config"] = config


@run_svm.command(name="install")
@click.argument("version_range", nargs=-1)
@click.option(
    "--force", is_flag=True, help="Reinstall the target version if already installed."
)
@click.pass_context
def svm_install(ctx: Context, version_range: Tuple[str], force: bool) -> None:
    """Install the latest solc version matching the given version range."""
    config: WokeConfig = ctx.obj["config"]
    svm = SolcVersionManager(config)
    version_expr = SolidityVersionExpr(" ".join(version_range))

    asyncio.run(run_solc_install(svm, version_expr, force))


async def run_solc_install(
    svm: SolcVersionManager, version_expr: SolidityVersionExpr, force: bool
) -> None:
    version = next(
        version for version in reversed(svm.list_all()) if version in version_expr
    )
    if not force and svm.get_path(version).is_file():
        console.print(f"Version {version} is already installed.")
        return

    with Progress() as progress:
        task = progress.add_task(f"[green]Downloading solc {version}")

        async def on_progress(downloaded: int, total: int) -> None:
            progress.update(task, completed=downloaded, total=total)

        await svm.install(
            version,
            force_reinstall=force,
            progress=on_progress,
        )
    console.print(f"Installed solc version {version}.")


@run_svm.command(name="switch")
@click.argument("version", nargs=1)
@click.pass_context
def svm_switch(ctx: Context, version: str) -> None:
    """Switch to the target version of solc. Raise an exception if the version is not installed."""
    config: WokeConfig = ctx.obj["config"]
    svm = SolcVersionManager(config)
    parsed_version = SolidityVersion.fromstring(version)

    if not svm.get_path(parsed_version).is_file():
        raise ValueError(f"solc version {parsed_version} is not installed.")

    (config.woke_root_path / ".woke_solc_version").write_text(str(parsed_version))
    console.print(f"Using woke-solc version {version}.")


@run_svm.command(name="use")
@click.argument("version_range", nargs=-1)
@click.option(
    "--force", is_flag=True, help="Reinstall the target version if already installed."
)
@click.pass_context
def svm_use(ctx: Context, version_range: Tuple[str], force: bool) -> None:
    """Install the target solc version and use it as the global version."""
    config: WokeConfig = ctx.obj["config"]
    svm = SolcVersionManager(config)
    version_expr = SolidityVersionExpr(" ".join(version_range))
    version = next(
        version for version in reversed(svm.list_all()) if version in version_expr
    )

    if not svm.get_path(version).is_file():
        asyncio.run(run_solc_install(svm, SolidityVersionExpr(str(version)), force))

    (config.woke_root_path / ".woke_solc_version").write_text(str(version))
    console.print(f"Using woke-solc version {version}.")


@run_svm.command(name="list")  # TODO alias `ls`
@click.option(
    "--all", is_flag=True, help="List all versions including non-installed ones."
)
@click.pass_context
def svm_list(ctx: Context, all: bool) -> None:
    """List installed solc versions."""
    config: WokeConfig = ctx.obj["config"]
    svm = SolcVersionManager(config)
    if all:
        installed = set(svm.list_installed())
        output = "\n".join(
            f"- {version} {'([green]installed[/green])' if version in installed else ''}"
            for version in svm.list_all()
        )
    else:
        output = "\n".join(f"- {version}" for version in svm.list_installed())
    console.print(output)


@run_svm.command(name="remove")  # TODO alias `rm`
@click.argument("version", nargs=1)
@click.option(
    "--ignore-missing",
    is_flag=True,
    help="do not raise an exception if version to be removed is not installed",
)
@click.pass_context
def svm_remove(ctx: Context, version: str, ignore_missing: bool) -> None:
    """Remove the target solc version."""
    config: WokeConfig = ctx.obj["config"]
    svm = SolcVersionManager(config)
    parsed_version = SolidityVersion.fromstring(version)

    if ignore_missing:
        try:
            svm.remove(parsed_version)
            console.print(f"Removed solc version {parsed_version}.")
        except ValueError:
            console.print(f"solc {parsed_version} is not installed.")
    else:
        svm.remove(parsed_version)
        console.print(f"Removed solc version {parsed_version}.")
