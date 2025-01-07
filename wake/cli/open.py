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
    from wake.development.utils import get_info_from_explorer
    from wake.svm import SolcVersionManager

    config = WakeConfig()
    config.load_configs()

    if project_dir is None:
        project_dir = (
            config.global_cache_path / "explorers" / str(chain_id) / address.lower()
        )

    link = config.general.link_format.format(
        path=str(project_dir),
        line=0,
        col=0,
    )

    if project_dir.exists() and not force:
        existing_files = list(project_dir.iterdir())
        if len(existing_files) != 1 or existing_files[0].name not in {
            "sourcify.json",
            "etherscan.json",
        }:
            console.print(
                f"{address} already exists at [link={link}]{project_dir}[/link]"
            )
            return

    project_dir.mkdir(parents=True, exist_ok=True)

    with console.status(f"Fetching {address} from explorer..."):
        info, source = get_info_from_explorer(address, chain_id, config)

    if source == "sourcify":
        metadata = json.loads(
            next(f for f in info["files"] if f["name"] == "metadata.json")["content"]
        )
        version = SolidityVersion.fromstring(metadata["compiler"]["version"])

        if any(
            f
            for f in info["files"]
            if f["name"].endswith(".sol") and PurePosixPath(f["name"]).is_absolute()
        ):
            raise NotImplementedError("Absolute paths are not supported")

        sources = {
            project_dir
            / PurePosixPath(*PurePosixPath(file["path"]).parts[5:]): file["content"]
            for file in info["files"]
            if file["name"].endswith(".sol")
        }

        config_dict = {
            "compiler": {
                "solc": {
                    "target_version": str(version),
                    "evm_version": metadata["settings"]["evmVersion"],
                    "remappings": metadata["settings"]["remappings"],
                    "optimizer": metadata["settings"]["optimizer"],
                }
            }
        }
    else:
        compiler_version: str = info["CompilerVersion"]
        if compiler_version.startswith("vyper"):
            raise ValueError("Cannot set balance of Vyper contract")

        if compiler_version.startswith("v"):
            compiler_version = compiler_version[1:]
        version = SolidityVersion.fromstring(compiler_version)

        optimizations = bool(info["OptimizationUsed"])
        runs = info["Runs"]

        config_dict = {
            "compiler": {
                "solc": {
                    "target_version": str(version),
                    "optimizer": {
                        "enabled": optimizations,
                        "runs": runs,
                    },
                }
            }
        }

        code = info["SourceCode"]
        try:
            standard_input: SolcInput = SolcInput.model_validate_json(code[1:-1])
            if any(
                PurePosixPath(filename).is_absolute()
                for filename in standard_input.sources.keys()
            ):
                raise NotImplementedError("Absolute paths are not supported")
            if standard_input.settings is not None:
                if standard_input.settings.evm_version is not None:
                    config_dict["compiler"]["solc"]["evm_version"] = str(
                        standard_input.settings.evm_version
                    )
                if standard_input.settings.via_IR is not None:
                    config_dict["compiler"]["solc"][
                        "via_IR"
                    ] = standard_input.settings.via_IR
                if standard_input.settings.remappings is not None:
                    config_dict["compiler"]["solc"][
                        "remappings"
                    ] = standard_input.settings.remappings
                if standard_input.settings.optimizer is not None:
                    if standard_input.settings.optimizer.enabled is not None:
                        config_dict["compiler"]["solc"]["optimizer"][
                            "enabled"
                        ] = standard_input.settings.optimizer.enabled
                    if standard_input.settings.optimizer.runs is not None:
                        config_dict["compiler"]["solc"]["optimizer"][
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
                    raise NotImplementedError("Absolute paths are not supported")

                sources = {
                    project_dir / path: source.content for path, source in s.items()
                }
            except (ValidationError, json.JSONDecodeError) as e:
                sources = {project_dir / "contracts" / "Source.sol": code}

    svm = SolcVersionManager(config)
    if not svm.installed(version):
        await svm.install(version)

    with console.status(f"Writing {address} to {project_dir}..."):
        for path, content in sources.items():
            if content is None:
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)

    project_dir.joinpath("wake.toml").write_text(tomli_w.dumps(config_dict))

    console.print(f"Opened {address} at [link={link}]{project_dir}[/link]")


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

    link = config.general.link_format.format(
        path=str(project_dir),
        line=0,
        col=0,
    )

    if project_dir.exists():
        if force:
            shutil.rmtree(project_dir)
        else:
            console.print(
                f"{owner}/{repo} already exists at [link={link}]{project_dir}[/link]"
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

    console.print(f"Opened {owner}/{repo} at [link={link}]{project_dir}[/link]")
