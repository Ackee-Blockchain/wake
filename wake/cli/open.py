from pathlib import Path, PurePosixPath
from typing import Any, Dict, Optional

import rich_click as click

from .console import console
from .param_types import Chain


@click.command(name="open")
@click.argument(
    "uri",
    type=str,
    required=True,
)
@click.option(
    "--chain",
    type=Chain(),
    default="mainnet",
    help="Chain name or ID for address",
)
@click.option(
    "--branch",
    "-b",
    type=str,
    help="Github branch to clone",
)
@click.option(
    "--path",
    "-p",
    type=click.Path(file_okay=False),
    help="Path where project should be created",
)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    default=False,
    help="Overwrite existing project",
)
def run_open(
    uri: str, chain: int, branch: Optional[str], path: Optional[str], force: bool
) -> None:
    """
    Fetch project from Github or Etherscan-like explorer.
    """
    import asyncio

    if force and path is not None:
        raise click.ClickException("Cannot use both --path and --force")

    try:
        if uri.lower().startswith("0x") and len(uri) == 42:
            int(uri, 16)
        elif len(uri) == 40:
            int(uri, 16)
        else:
            raise ValueError()

        # ethereum address
        asyncio.run(
            open_address(
                uri, chain, None if path is None else Path(path).resolve(), force
            )
        )
    except ValueError:
        # github repository
        open_github(uri, branch, None if path is None else Path(path).resolve(), force)


async def open_address(
    address: str, chain_id: int, project_dir: Optional[Path], force: bool
) -> None:
    import json
    import urllib.request

    import tomli_w
    from pydantic import TypeAdapter, ValidationError

    from wake.compiler.solc_frontend import SolcInput, SolcInputSource
    from wake.config import WakeConfig
    from wake.core.solidity_version import SolidityVersion
    from wake.development.utils import chain_explorer_urls
    from wake.svm import SolcVersionManager

    config = WakeConfig()
    config.load_configs()

    try:
        chain_explorer = chain_explorer_urls[chain_id]
    except KeyError:
        raise ValueError("Invalid chain") from None

    api_key = config.api_keys.get(chain_explorer.config_key, None)

    if project_dir is None:
        project_dir = (
            config.global_cache_path / "explorers" / str(chain_id) / address.lower()
        )
    if project_dir.exists() and not force:
        console.print(
            f"{address} already exists at [link=vscode://file/{project_dir}]{project_dir}[/link]"
        )
        return

    project_dir.mkdir(parents=True, exist_ok=True)

    url = (
        chain_explorer_urls[chain_id].api_url
        + f"?module=contract&action=getsourcecode&address={address}"
    )
    if api_key is not None:
        url += f"&apikey={api_key}"

    with console.status(
        f"Fetching {address} from {chain_explorer_urls[chain_id].url}..."
    ):
        with urllib.request.urlopen(url) as response:
            parsed = json.loads(response.read())

    version: str = parsed["result"][0]["CompilerVersion"]
    if version.startswith("vyper"):
        raise NotImplementedError("Vyper contracts are not supported")

    if version.startswith("v"):
        version = version[1:]
    parsed_version = SolidityVersion.fromstring(version)

    project_config_raw: Dict[str, Any] = {
        "compiler": {
            "solc": {
                "optimizer": {
                    "enabled": bool(parsed["result"][0]["OptimizationUsed"]),
                    "runs": parsed["result"][0]["Runs"],
                }
            }
        }
    }

    svm = SolcVersionManager(config)
    if not svm.installed(parsed_version):
        await svm.install(parsed_version)

    code = parsed["result"][0]["SourceCode"]
    try:
        standard_input: SolcInput = SolcInput.model_validate_json(code[1:-1])
        if any(
            PurePosixPath(filename).is_absolute()
            for filename in standard_input.sources.keys()
        ):
            raise ValueError("Absolute paths are not supported")
        if standard_input.settings is not None:
            if standard_input.settings.evm_version is not None:
                project_config_raw["compiler"]["solc"]["evm_version"] = str(
                    standard_input.settings.evm_version
                )
            if standard_input.settings.via_IR is not None:
                project_config_raw["compiler"]["solc"][
                    "via_IR"
                ] = standard_input.settings.via_IR
            if standard_input.settings.remappings is not None:
                project_config_raw["compiler"]["solc"][
                    "remappings"
                ] = standard_input.settings.remappings
            if standard_input.settings.optimizer is not None:
                if standard_input.settings.optimizer.enabled is not None:
                    project_config_raw["compiler"]["solc"]["optimizer"][
                        "enabled"
                    ] = standard_input.settings.optimizer.enabled
                if standard_input.settings.optimizer.runs is not None:
                    project_config_raw["compiler"]["solc"]["optimizer"][
                        "runs"
                    ] = standard_input.settings.optimizer.runs
                # TODO optimizer details

        sources = {
            project_dir / path: source.content
            for path, source in standard_input.sources.items()
        }
    except ValidationError as e:
        try:
            a = TypeAdapter(Dict[str, SolcInputSource])
            s = a.validate_json(code)
            if any(PurePosixPath(filename).is_absolute() for filename in s.keys()):
                raise ValueError("Absolute paths are not supported")

            sources = {project_dir / path: source.content for path, source in s.items()}
        except (ValidationError, json.JSONDecodeError) as e:
            sources = {project_dir / "contracts" / "Source.sol": code}

    with console.status(f"Writing {address} to {project_dir}..."):
        for path, content in sources.items():
            if content is None:
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)

    project_dir.joinpath("wake.toml").write_text(tomli_w.dumps(project_config_raw))

    console.print(
        f"Opened {address} at [link=vscode://file/{project_dir}]{project_dir}[/link]"
    )


def open_github(
    uri: str, branch: Optional[str], project_dir: Optional[Path], force: bool
) -> None:
    import shutil
    import subprocess
    from urllib.parse import urlparse

    from wake.config import WakeConfig

    config = WakeConfig()
    config.load_configs()

    parsed_uri = urlparse(uri)
    if parsed_uri.netloc == "github.com" and parsed_uri.path:
        path_parts = parsed_uri.path.strip("/").split("/")
        if len(path_parts) == 2:
            owner, repo = path_parts
        elif len(path_parts) == 3:
            owner, repo, branch = path_parts
        elif len(path_parts) == 4 and path_parts[2] == "tree":
            owner, repo, branch = path_parts[:2] + path_parts[3:]
        else:
            raise ValueError("Invalid github repository")
    elif uri.startswith("git@github.com"):
        owner, repo = uri.split(":")[1].split("/")
    else:
        raise ValueError("Invalid github repository")

    if repo.endswith(".git"):
        repo = repo[:-4]

    if project_dir is None:
        project_dir = config.global_cache_path / "github" / owner / repo
    if project_dir.exists():
        if force:
            shutil.rmtree(project_dir)
        else:
            console.print(
                f"{owner}/{repo} already exists at [link=vscode://file/{project_dir}]{project_dir}[/link]"
            )
            return

    project_dir.parent.mkdir(parents=True, exist_ok=True)

    if branch is None:
        subprocess.run(["git", "clone", uri, "--recursive"], cwd=project_dir.parent)
    else:
        subprocess.run(
            ["git", "clone", uri, "--recursive", "--branch", branch],
            cwd=project_dir.parent,
        )

    console.print(
        f"Opened {owner}/{repo} at [link=vscode://file/{project_dir}]{project_dir}[/link]"
    )
