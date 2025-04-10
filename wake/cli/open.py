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
@click.option(
    "--export",
    type=click.Choice(["json"]),
)
def run_open(
    uri: str,
    chain: int,
    branch: Optional[str],
    path: Optional[str],
    force: bool,
    export: Optional[str],
) -> None:
    """
    Fetch project from Github or Etherscan-like explorer.
    """
    import asyncio

    if force and path is not None:
        raise click.ClickException("Cannot use both --path and --force")

    # ethereum address
    if all(char in "xabcdef0123456789" for char in uri.lower()):
        try:
            if uri.lower().startswith("0x") and len(uri) == 42:
                int(uri, 16)
            elif not uri.lower().startswith("0x") and len(uri) == 40:
                int(uri, 16)
                uri = "0x" + uri
            else:
                raise ValueError()
        except ValueError:
            raise ValueError("Invalid ethereum address")

        asyncio.run(
            open_address(
                uri,
                chain,
                None if path is None else Path(path).resolve(),
                force,
                export,
            )
        )

    # github repository
    else:
        if export is not None:
            raise click.ClickException(
                "Exporting to file is not supported for github repositories"
            )
        open_github(uri, branch, None if path is None else Path(path).resolve(), force)


async def open_address(
    address: str,
    chain_id: int,
    project_dir: Optional[Path],
    force: bool,
    export: Optional[str],
) -> None:
    import json
    import sys

    import tomli_w
    from pydantic import TypeAdapter, ValidationError

    from wake.compiler.solc_frontend import SolcInput, SolcInputSource
    from wake.config import WakeConfig
    from wake.core import get_logger
    from wake.core.solidity_version import SolidityVersion
    from wake.development.utils import get_info_from_explorer
    from wake.svm import SolcVersionManager

    logger = get_logger(__name__)

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

    if (
        project_dir.exists()
        and any(project_dir.iterdir())
        and not force
        and export is None
    ):
        existing_files = list(project_dir.iterdir())
        if not all(
            f.name
            in {
                "sourcify.json",
                "sourcify_v2.json",
                "etherscan.json",
                ".wake",
            }
            for f in existing_files
        ):
            console.print(
                f"{address} already exists at [link={link}]{project_dir}[/link]"
            )
            return

    with console.status(f"Fetching {address} from explorer..."):
        info, source = get_info_from_explorer(address, chain_id, config, force=force)

    if source == "sourcify":
        version = SolidityVersion.fromstring(info["compilation"]["compilerVersion"])
        name = info["compilation"]["name"]
        full_name = info["compilation"]["fullyQualifiedName"]

        if info["compilation"]["language"] != "Solidity":
            logger.error("Only Solidity contracts are supported")
            sys.exit(64)

        if any(
            "content" not in s or s["content"] is None for s in info["sources"].values()
        ):
            logger.error("Reading Solidity source code from URL is not supported")
            sys.exit(65)

        sources = {
            source_unit_name: content["content"]
            for source_unit_name, content in info["sources"].items()
        }

        config_dict = {"compiler": {"solc": {"target_version": str(version)}}}

        c = info["compilation"]["compilerSettings"]
        if "optimizer" in c:
            config_dict["compiler"]["solc"]["optimizer"] = {}
            if "enabled" in c["optimizer"]:
                config_dict["compiler"]["solc"]["optimizer"]["enabled"] = c[
                    "optimizer"
                ]["enabled"]
            if "runs" in c["optimizer"]:
                config_dict["compiler"]["solc"]["optimizer"]["runs"] = c["optimizer"][
                    "runs"
                ]

        if "remappings" in c:
            config_dict["compiler"]["solc"]["remappings"] = c["remappings"]

        if "evmVersion" in c:
            config_dict["compiler"]["solc"]["evm_version"] = c["evmVersion"]

        if "viaIR" in c:
            config_dict["compiler"]["solc"]["via_IR"] = c["viaIR"]
    else:
        compiler_version: str = info["CompilerVersion"]
        if compiler_version.startswith("vyper"):
            logger.error("Vyper contracts are not supported")
            sys.exit(64)

        if compiler_version.startswith("v"):
            compiler_version = compiler_version[1:]
        version = SolidityVersion.fromstring(compiler_version)
        name = info["ContractName"]
        full_name = None

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

            if any(s.content is None for s in standard_input.sources.values()):
                logger.error("Reading Solidity source code from URL is not supported")
                sys.exit(65)

            sources = {
                path: source.content for path, source in standard_input.sources.items()
            }
        except ValidationError as e:
            try:
                a = TypeAdapter(Dict[str, SolcInputSource])
                s = a.validate_json(code)

                if any(source.content is None for source in s.values()):
                    logger.error(
                        "Reading Solidity source code from URL is not supported"
                    )
                    sys.exit(65)

                sources = {path: source.content for path, source in s.items()}
            except (ValidationError, json.JSONDecodeError) as e:
                sources = {"contracts/Source.sol": code}

    if export == "json":
        import platform

        from wake.utils import get_package_version

        out = {
            "version": get_package_version("eth-wake"),
            "system": platform.system(),
            "project_root": str(project_dir),
            "wake_contracts_path": str(config.wake_contracts_path),
            "config": config_dict,
            "sources": {
                str(project_dir / k): {"content": v} for k, v in sources.items()
            },
            "extra": {
                "name": name,
            },
        }

        if full_name is not None:
            out["extra"]["full_name"] = full_name

        output_dir = project_dir / ".wake"
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "sources.json").write_text(json.dumps(out))
    elif export is not None:
        raise click.ClickException("Invalid export format")
    else:
        from wake.utils import is_relative_to

        if any(PurePosixPath(f).is_absolute() for f in sources.keys()):
            logger.error("Absolute paths are not supported")
            sys.exit(66)

        svm = SolcVersionManager(config)
        if not svm.installed(version):
            await svm.install(version)

        with console.status(f"Writing {address} to {project_dir}..."):
            for source_unit_name, content in sources.items():
                path = project_dir / source_unit_name

                if not is_relative_to(path, project_dir):
                    logger.error(
                        "Relative paths outside of project directory are not supported"
                    )
                    sys.exit(67)

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
