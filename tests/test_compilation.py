import asyncio
import os
import platform
import shutil
import stat
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner
from git import Repo  # type: ignore

from woke.cli.__main__ import main
from woke.compiler import SolcOutputSelectionEnum, SolidityCompiler
from woke.config import WokeConfig
from woke.utils import change_cwd

PYTEST_BUILD_PATH = Path.home() / ".tmpwoke_rkDv61DDf7"


@pytest.fixture()
def config():
    os.environ["XDG_CONFIG_HOME"] = str(PYTEST_BUILD_PATH)
    os.environ["XDG_DATA_HOME"] = str(PYTEST_BUILD_PATH)
    config_dict = {"compiler": {"solc": {"include_paths": ["./node_modules"]}}}
    return WokeConfig.fromdict(
        config_dict,
        project_root_path=PYTEST_BUILD_PATH,
    )


@pytest.fixture()
def setup_project(request):
    clone_url = request.param
    repo = None

    try:
        repo = Repo.clone_from(
            clone_url, PYTEST_BUILD_PATH, multi_options=["--depth=1"]
        )
        subprocess.run(
            ["yarn", "install"],
            cwd=PYTEST_BUILD_PATH,
            shell=(platform.system() == "Windows"),
        )

        yield
    finally:

        def onerror(func, path, exc_info):
            if not os.access(path, os.W_OK):
                os.chmod(path, stat.S_IWUSR)
                func(path)
            else:
                raise

        if repo is not None:
            repo.close()
        shutil.rmtree(PYTEST_BUILD_PATH, onerror=onerror)


@pytest.mark.slow
@pytest.mark.parametrize(
    "setup_project", [r"https://github.com/Uniswap/v3-core.git"], indirect=True
)
def test_compile_uniswap_v3(setup_project, config):
    files = list((PYTEST_BUILD_PATH / "contracts").rglob("*.sol"))
    compiler = SolidityCompiler(config)
    output = asyncio.run(compiler.compile(files, [SolcOutputSelectionEnum.ALL]))
    assert len(output)

    output = asyncio.run(compiler.compile(files, [SolcOutputSelectionEnum.ALL]))
    assert len(output)

    (PYTEST_BUILD_PATH / "woke.toml").write_text(
        """
        [compiler.solc]
        ignore_paths = ["node_modules", "audits"]
        """
    )

    cli_runner = CliRunner()
    with change_cwd(PYTEST_BUILD_PATH):
        cli_result = cli_runner.invoke(
            main,
            ["compile"],
            env={
                "XDG_CONFIG_HOME": str(PYTEST_BUILD_PATH),
                "XDG_DATA_HOME": str(PYTEST_BUILD_PATH),
            },
        )
    assert cli_result.exit_code == 0


@pytest.mark.slow
@pytest.mark.parametrize(
    "setup_project", [r"https://github.com/graphprotocol/contracts.git"], indirect=True
)
def test_compile_the_graph(setup_project, config):
    files = list((PYTEST_BUILD_PATH / "contracts").rglob("*.sol"))
    compiler = SolidityCompiler(config)
    output = asyncio.run(compiler.compile(files, [SolcOutputSelectionEnum.ALL]))
    assert len(output)

    compiler = SolidityCompiler(config)
    output = asyncio.run(compiler.compile(files, [SolcOutputSelectionEnum.ALL]))
    assert len(output)

    cli_runner = CliRunner()
    with change_cwd(PYTEST_BUILD_PATH):
        cli_result = cli_runner.invoke(
            main,
            ["compile"],
            env={
                "XDG_CONFIG_HOME": str(PYTEST_BUILD_PATH),
                "XDG_DATA_HOME": str(PYTEST_BUILD_PATH),
            },
        )
    assert cli_result.exit_code == 0


@pytest.mark.slow
@pytest.mark.parametrize(
    "setup_project", [r"https://github.com/traderjoe-xyz/joe-core.git"], indirect=True
)
def test_compile_trader_joe(setup_project, config):
    files = list((PYTEST_BUILD_PATH / "contracts").rglob("*.sol"))
    compiler = SolidityCompiler(config)
    output = asyncio.run(
        compiler.compile(
            files,
            [SolcOutputSelectionEnum.ALL],
        )
    )
    assert len(output)

    output = asyncio.run(
        compiler.compile(
            files,
            [SolcOutputSelectionEnum.ALL],
        )
    )
    assert len(output)

    cli_runner = CliRunner()
    with change_cwd(PYTEST_BUILD_PATH):
        cli_result = cli_runner.invoke(
            main,
            ["compile"],
            env={
                "XDG_CONFIG_HOME": str(PYTEST_BUILD_PATH),
                "XDG_DATA_HOME": str(PYTEST_BUILD_PATH),
            },
        )
    assert cli_result.exit_code == 0


@pytest.mark.slow
@pytest.mark.parametrize(
    "setup_project",
    [r"https://github.com/axelarnetwork/axelar-cgp-solidity.git"],
    indirect=True,
)
def test_compile_axelar(setup_project, config):
    files = list((PYTEST_BUILD_PATH / "contracts").rglob("*.sol"))
    compiler = SolidityCompiler(config)
    output = asyncio.run(compiler.compile(files, [SolcOutputSelectionEnum.ALL]))
    assert len(output)

    output = asyncio.run(compiler.compile(files, [SolcOutputSelectionEnum.ALL]))
    assert len(output)

    (PYTEST_BUILD_PATH / "woke.toml").write_text(
        """
        [compiler.solc.optimizer]
        enabled = true
        """
    )

    cli_runner = CliRunner()
    with change_cwd(PYTEST_BUILD_PATH):
        cli_result = cli_runner.invoke(
            main,
            ["compile"],
            env={
                "XDG_CONFIG_HOME": str(PYTEST_BUILD_PATH),
                "XDG_DATA_HOME": str(PYTEST_BUILD_PATH),
            },
        )
    assert cli_result.exit_code == 0
