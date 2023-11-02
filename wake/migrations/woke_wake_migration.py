import os
import platform
import shutil
from pathlib import Path

import rich_click as click
import tomli
import tomli_w

from ..cli.console import console


def migrate_config_file(old_path: Path, new_path: Path) -> None:
    def rename_file():
        try:
            old_path.rename(new_path)
            # TODO suggest user to edit new config file appropriately
            console.print(
                f"[green]• Moved old config file {old_path} to {new_path} ✅[/]"
            )
        except OSError:
            console.print(
                f"[red]• Failed to move old config file {old_path} to {new_path} ❌[/]"
            )

    try:
        old_config = tomli.loads(old_path.read_text())
        try:
            ignore_paths = old_config["compiler"]["solc"]["ignore_paths"]
            old_config["compiler"]["solc"]["exclude_paths"] = ignore_paths
            del old_config["compiler"]["solc"]["ignore_paths"]
        except KeyError:
            pass
        try:
            ignore_paths = old_config["detectors"]["ignore_paths"]
            old_config["detectors"]["exclude_paths"] = ignore_paths
            del old_config["detectors"]["ignore_paths"]
        except KeyError:
            pass

        try:
            timeout = old_config["testing"]["timeout"]
            old_config["general"]["json_rpc_timeout"] = timeout
            del old_config["testing"]["timeout"]
        except KeyError:
            pass

        try:
            new_path.write_text(tomli_w.dumps(old_config))
            console.print(
                f"[green]• Migrated old config file {old_path} to {new_path} ✅[/]"
            )
            try:
                old_path.unlink()
                console.print(f"[green]• Removed old config file {old_path} ✅[/]")
            except OSError:
                console.print(
                    f"[red]• Failed to remove old config file {old_path} ❌[/]"
                )
        except OSError:
            console.print(f"[red]• Failed to write new config file {new_path} ❌[/]")
            rename_file()
    except tomli.TOMLDecodeError:
        console.print(f"[red]• Failed to parse old config file {old_path} ❌[/]")
        rename_file()
    except OSError:
        console.print(f"[red]• Failed to read old config file {old_path} ❌[/]")
        rename_file()


def run_woke_wake_migration() -> None:
    system = platform.system()

    try:
        xdg_config_path = Path(os.environ["XDG_CONFIG_HOME"])
    except KeyError:
        if system in {"Linux", "Darwin"}:
            xdg_config_path = Path.home() / ".config"
        elif system == "Windows":
            xdg_config_path = Path(os.environ["LOCALAPPDATA"])
        else:
            raise RuntimeError(f"Platform `{system}` is not supported.")

    old_global_config_path = xdg_config_path / "woke" / "config.toml"
    old_local_config_path = Path.cwd() / "woke.toml"

    try:
        xdg_data_path = Path(os.environ["XDG_DATA_HOME"])
    except KeyError:
        if system in {"Linux", "Darwin"}:
            xdg_data_path = Path.home() / ".local" / "share"
        elif system == "Windows":
            xdg_data_path = Path(os.environ["LOCALAPPDATA"])
        else:
            raise RuntimeError(f"Platform `{system}` is not supported.")

    old_global_data_path = xdg_data_path / "woke"

    if (
        not old_global_config_path.exists()
        and not old_global_data_path.exists()
        and not old_local_config_path.exists()
    ):
        return

    console.print(
        "[bold green]Woke is Wake now[/] [blue]🌊🌊[/] [bold green](see more at [link=https://getwake.io]getwake.io[/link])[/]"
    )

    # global files

    if old_global_config_path.exists():
        new_global_config_path = xdg_config_path / "wake" / "config.toml"
        try:
            new_global_config_path.parent.mkdir(exist_ok=True)
            migrate_config_file(old_global_config_path, new_global_config_path)
        except OSError:
            console.print(
                f"[red]• Failed to create new global config directory {new_global_config_path.parent} ❌[/]"
            )

    if old_global_data_path.exists():
        new_global_data_path = xdg_data_path / "wake"
        try:
            old_global_data_path.rename(new_global_data_path)
            console.print(
                f"[green]• Moved old global data directory {old_global_data_path} to {new_global_data_path} ✅[/]"
            )

            old_solc_version_path = new_global_data_path / ".woke_solc_version"
            new_solc_version_path = new_global_data_path / "solc-version.txt"
            try:
                old_solc_version_path.rename(new_solc_version_path)
                console.print(
                    f"[green]• Moved old solc version file {old_solc_version_path} to {new_solc_version_path} ✅[/]"
                )
            except OSError:
                console.print(
                    f"[red]• Failed to move old solc version file {old_solc_version_path} to {new_solc_version_path} ❌[/]"
                )
        except OSError:
            console.print(
                f"[red]• Failed to move old global data directory {old_global_data_path} to {new_global_data_path} ❌[/]"
            )
            try:
                shutil.rmtree(old_global_data_path)
            except OSError:
                console.print(
                    f"[red]• Failed to remove old global data directory {old_global_data_path} ❌[/]]"
                )

    # local files

    old_build_path = Path.cwd() / ".woke-build"
    old_logs_path = Path.cwd() / ".woke-logs"
    old_prof_path = Path.cwd() / "woke.prof"
    old_coverage_path = Path.cwd() / "woke-coverage.cov"
    gitignore_path = Path.cwd() / ".gitignore"
    wake_path = Path.cwd() / ".wake"

    if old_local_config_path.exists():
        ctx = click.get_current_context(silent=True)
        if ctx is None or ctx.obj.get("local_config_path", None) is None:
            new_local_config_path = Path.cwd() / "wake.toml"
        else:
            new_local_config_path = Path(
                ctx.obj.get("local_config_path", "./wake.toml")
            ).resolve()

        migrate_config_file(old_local_config_path, new_local_config_path)
    else:
        # don't perform local file migrations if there is no local config file
        return

    if gitignore_path.exists():
        try:
            with gitignore_path.open("r") as f:
                lines = f.readlines()
            with gitignore_path.open("w") as f:
                for line in lines:
                    if line.strip() in {
                        ".woke-build",
                        ".woke-logs",
                        "woke-coverage.cov",
                    }:
                        continue
                    f.write(line)
                f.write(".wake\n")
                f.write("wake-coverage.cov\n")
            console.print(f"[green]• Updated .gitignore ✅[/]")
        except OSError:
            console.print(f"[red]• Failed to update .gitignore ❌[/]")

    if old_coverage_path.exists():
        new_coverage_path = Path.cwd() / "wake-coverage.cov"
        try:
            old_coverage_path.rename(new_coverage_path)
            console.print(
                f"[green]• Moved old coverage file {old_coverage_path} to {new_coverage_path} ✅[/]"
            )
        except OSError:
            console.print(
                f"[red]• Failed to move old coverage file {old_coverage_path} to {new_coverage_path} ❌[/]"
            )

    if old_build_path.exists():
        try:
            shutil.rmtree(old_build_path)
            console.print(f"[green]• Removed old build directory {old_build_path} ✅[/]")
        except OSError:
            console.print(
                f"[red]• Failed to remove old build directory {old_build_path} ❌[/]"
            )

    try:
        wake_path.mkdir(exist_ok=True)
        console.print(f"[green]• Created .wake directory ✅[/]")
    except OSError:
        console.print(f"[red]• Failed to create .wake directory ❌[/]")
        # other steps require .wake directory to exist
        return

    if old_logs_path.exists():
        new_logs_path = wake_path / "logs"
        try:
            old_logs_path.rename(new_logs_path)
            console.print(
                f"[green]• Moved old logs directory {old_logs_path} to {new_logs_path} ✅[/]"
            )
        except OSError:
            console.print(
                f"[red]• Failed to move old logs directory {old_logs_path} to {new_logs_path} ❌[/]"
            )

    if old_prof_path.exists():
        new_prof_path = wake_path / "wake.prof"
        try:
            old_prof_path.rename(new_prof_path)
            console.print(
                f"[green]• Moved old profiling file {old_prof_path} to {new_prof_path} ✅[/]"
            )
        except OSError:
            console.print(
                f"[red]• Failed to move old profiling file {old_prof_path} to {new_prof_path} ❌[/]"
            )
