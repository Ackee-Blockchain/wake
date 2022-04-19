import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest
from git import Repo  # type: ignore

from woke.a_config import WokeConfig
from woke.d_compile import SolidityCompiler, SolcOutputSelectionEnum


PYTEST_BUILD_PATH = Path.home() / ".tmpwoke_rkDv61DDf7"


@pytest.fixture()
def config():
    config_dict = {"compiler": {"solc": {"include_paths": ["./node_modules"]}}}
    return WokeConfig.fromdict(
        config_dict,
        woke_root_path=PYTEST_BUILD_PATH,
        project_root_path=PYTEST_BUILD_PATH,
    )


@pytest.fixture()
def setup_project(request):
    clone_url = request.param
    repo = None

    try:
        repo = Repo.clone_from(clone_url, PYTEST_BUILD_PATH)
        subprocess.run(["npm", "install"], cwd=PYTEST_BUILD_PATH, shell=True)

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
async def test_compile_uniswap_v3(setup_project, config):
    files = list((PYTEST_BUILD_PATH / "contracts").rglob("*.sol"))
    compiler = SolidityCompiler(config, files)
    output = await compiler.compile(SolcOutputSelectionEnum.ALL, reuse_latest_artifacts=False)  # type: ignore
    assert len(output)

    compiler = SolidityCompiler(config, files)
    output = await compiler.compile(SolcOutputSelectionEnum.ALL, reuse_latest_artifacts=True)  # type: ignore
    assert len(output)


@pytest.mark.slow
@pytest.mark.parametrize(
    "setup_project", [r"https://github.com/graphprotocol/contracts.git"], indirect=True
)
async def test_compile_the_graph(setup_project, config):
    files = list((PYTEST_BUILD_PATH / "contracts").rglob("*.sol"))
    compiler = SolidityCompiler(config, files)
    output = await compiler.compile(SolcOutputSelectionEnum.ALL, reuse_latest_artifacts=False)  # type: ignore
    assert len(output)

    compiler = SolidityCompiler(config, files)
    output = await compiler.compile(SolcOutputSelectionEnum.ALL, reuse_latest_artifacts=True)  # type: ignore
    assert len(output)


@pytest.mark.slow
@pytest.mark.parametrize(
    "setup_project", [r"https://github.com/traderjoe-xyz/joe-core.git"], indirect=True
)
async def test_compile_trader_joe(setup_project, config):
    files = list((PYTEST_BUILD_PATH / "contracts").rglob("*.sol"))
    compiler = SolidityCompiler(config, files)
    output = await compiler.compile(SolcOutputSelectionEnum.ALL, reuse_latest_artifacts=False)  # type: ignore
    assert len(output)

    compiler = SolidityCompiler(config, files)
    output = await compiler.compile(SolcOutputSelectionEnum.ALL, reuse_latest_artifacts=True)  # type: ignore
    assert len(output)


@pytest.mark.slow
@pytest.mark.parametrize(
    "setup_project",
    [r"https://github.com/axelarnetwork/axelar-cgp-solidity.git"],
    indirect=True,
)
async def test_compile_axelar(setup_project, config):
    files = list((PYTEST_BUILD_PATH / "src").rglob("*.sol"))
    compiler = SolidityCompiler(config, files)
    output = await compiler.compile(SolcOutputSelectionEnum.ALL, reuse_latest_artifacts=False)  # type: ignore
    assert len(output)

    compiler = SolidityCompiler(config, files)
    output = await compiler.compile(SolcOutputSelectionEnum.ALL, reuse_latest_artifacts=True)  # type: ignore
    assert len(output)
