import os
import platform
import shutil
from pathlib import Path

from ..cli.console import console


def run_xdg_migration() -> None:
    system = platform.system()

    if system == "Linux":
        old_path = Path.home() / ".config" / "Woke"
    elif system == "Darwin":
        old_path = Path.home() / ".config" / "Woke"
    elif system == "Windows":
        old_path = Path.home() / "Woke"
    else:
        raise RuntimeError(f"Platform `{system}` is not supported.")

    if not old_path.exists():
        return

    config_path = old_path / "config.toml"
    compilers_path = old_path / "compilers"
    solc_versions_path = old_path / ".woke_solc_version"

    try:
        global_config_path = (
            Path(os.environ["XDG_CONFIG_HOME"]) / "woke" / "config.toml"
        )
    except KeyError:
        if system in {"Linux", "Darwin"}:
            global_config_path = Path.home() / ".config" / "woke" / "config.toml"
        elif system == "Windows":
            global_config_path = (
                Path(os.environ["LOCALAPPDATA"]) / "woke" / "config.toml"
            )
        else:
            raise RuntimeError(f"Platform `{system}` is not supported.")

    try:
        global_data_path = Path(os.environ["XDG_DATA_HOME"]) / "woke"
    except KeyError:
        if system in {"Linux", "Darwin"}:
            global_data_path = Path.home() / ".local" / "share" / "woke"
        elif system == "Windows":
            global_data_path = Path(os.environ["LOCALAPPDATA"]) / "woke"
        else:
            raise RuntimeError(f"Platform `{system}` is not supported.")

    global_config_path.parent.mkdir(parents=True, exist_ok=True)
    global_data_path.mkdir(parents=True, exist_ok=True)

    if config_path.exists():
        try:
            config_path.rename(global_config_path)
            console.print(
                f"[green]Moved config file from {config_path} to {global_config_path} ✅[/]"
            )
        except OSError:
            console.print(
                f"[red]Failed to move config file from {config_path} to {global_config_path} ❌[/]"
            )
    if compilers_path.exists():
        try:
            compilers_path.rename(global_data_path / "compilers")
            console.print(
                f"[green]Moved compilers directory from {compilers_path} to {global_data_path / 'compilers'} ✅[/]"
            )
        except OSError:
            console.print(
                f"[red]Failed to move compilers directory from {compilers_path} to {global_data_path / 'compilers'} ❌[/]"
            )

    if solc_versions_path.exists():
        try:
            solc_versions_path.rename(global_data_path / ".woke_solc_version")
            console.print(
                f"[green]Moved target solc versions file from {solc_versions_path} to {global_data_path / '.woke_solc_version'} ✅[/]"
            )
        except OSError:
            console.print(
                f"[red]Failed to move target solc versions file from {solc_versions_path} to {global_data_path / '.woke_solc_version'} ❌[/]"
            )

    try:
        shutil.rmtree(old_path)
        console.print(f"[green]Removed old config directory {old_path} ✅[/]")
    except OSError:
        console.print(f"[red]Unable to remove old config directory {old_path} ❌[/]")
