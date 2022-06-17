import asyncio
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional, Union

import aiohttp
import pytest

from woke.config import WokeConfig
from woke.svm import SolcVersionManager
from woke.svm.exceptions import UnsupportedVersionError

PYTEST_WOKE_PATH = Path.home() / ".tmpwoke_KVUhSovO5J"
PYTEST_WOKE_PATH2 = Path.home() / ".tmpwoke2_fLtqXkHeVH"


@pytest.fixture()
def run_cleanup(request):
    yield

    paths: Optional[List[Union[str, Path]]] = request.param
    if paths is not None:
        for path in paths:
            shutil.rmtree(path, True)


@pytest.fixture()
def config():
    return WokeConfig(woke_root_path=PYTEST_WOKE_PATH)


@pytest.fixture()
def config2():
    return WokeConfig(woke_root_path=PYTEST_WOKE_PATH2)


@pytest.mark.slow
@pytest.mark.platform_dependent
@pytest.mark.parametrize("run_cleanup", [[PYTEST_WOKE_PATH]], indirect=True)
async def test_basic_usage(run_cleanup, config):
    svm = SolcVersionManager(config)

    assert len(svm.list_installed()) == 0
    assert "0.8.10" in svm.list_all()
    await svm.install("0.8.10")
    assert len(svm.list_installed()) == 1
    assert "0.8.10" in svm.list_installed()
    await svm.install("0.8.10")  # repeat the installation
    assert len(svm.list_installed()) == 1
    assert "0.8.10" in svm.list_installed()
    svm.remove("0.8.10")
    assert len(svm.list_installed()) == 0

    with pytest.raises(UnsupportedVersionError):
        await svm.install("0.1.2")


@pytest.mark.slow
@pytest.mark.platform_dependent
@pytest.mark.parametrize("run_cleanup", [[PYTEST_WOKE_PATH]], indirect=True)
async def test_parallel_install(run_cleanup, config):
    svm = SolcVersionManager(config)
    to_be_installed = [f"0.8.{x}" for x in range(5)]

    async with aiohttp.ClientSession() as session:
        await asyncio.gather(
            *[svm.install(version, http_session=session) for version in to_be_installed]
        )

    installed = svm.list_installed()
    assert len(installed) == len(to_be_installed)
    for version in to_be_installed:
        assert version in installed


@pytest.mark.platform_dependent
@pytest.mark.parametrize("run_cleanup", [[PYTEST_WOKE_PATH]], indirect=True)
async def test_install_invalid_version(run_cleanup, config):
    svm = SolcVersionManager(config)
    with pytest.raises(ValueError):
        await svm.install("0.8.a")
    assert len(svm.list_installed()) == 0


@pytest.mark.slow
@pytest.mark.platform_dependent
@pytest.mark.parametrize(
    "run_cleanup", [[PYTEST_WOKE_PATH, PYTEST_WOKE_PATH2]], indirect=True
)
async def test_two_woke_root_paths(run_cleanup, config, config2):
    svm1 = SolcVersionManager(config)
    svm2 = SolcVersionManager(config2)

    assert "0.8.10" in svm1.list_all()
    assert "0.8.9" in svm2.list_all()
    assert len(svm1.list_installed()) == 0
    assert len(svm2.list_installed()) == 0
    await svm1.install("0.8.10")
    await svm2.install("0.8.9")
    assert "0.8.10" in svm1.list_installed()
    assert "0.8.9" not in svm1.list_installed()
    assert "0.8.9" in svm2.list_installed()
    assert "0.8.10" not in svm2.list_installed()


@pytest.mark.platform_dependent
@pytest.mark.parametrize("run_cleanup", [[PYTEST_WOKE_PATH]], indirect=True)
def test_remove_not_installed_version(run_cleanup, config):
    svm = SolcVersionManager(config)
    with pytest.raises(ValueError):
        svm.remove("0.8.10")


@pytest.mark.platform_dependent
@pytest.mark.parametrize("run_cleanup", [[PYTEST_WOKE_PATH]], indirect=True)
async def test_install_nonexistent_version(run_cleanup, config):
    svm = SolcVersionManager(config)
    with pytest.raises(UnsupportedVersionError):
        await svm.install("0.0.0")
    with pytest.raises(ValueError):
        await svm.install("0.4.100")


@pytest.mark.slow
@pytest.mark.platform_dependent
@pytest.mark.parametrize("run_cleanup", [[PYTEST_WOKE_PATH]], indirect=True)
async def test_install_aiohttp_session(run_cleanup, config):
    svm = SolcVersionManager(config)
    async with aiohttp.ClientSession() as session:
        await svm.install("0.8.10", http_session=session)
        assert len(svm.list_installed()) == 1
        assert "0.8.10" in svm.list_installed()


@pytest.mark.platform_dependent
@pytest.mark.parametrize("run_cleanup", [[PYTEST_WOKE_PATH]], indirect=True)
async def test_get_path_nonexistent_version(run_cleanup, config):
    svm = SolcVersionManager(config)
    with pytest.raises(UnsupportedVersionError):
        svm.get_path("0.0.0")
    with pytest.raises(ValueError):
        svm.get_path("0.4.255")


@pytest.mark.slow
@pytest.mark.platform_dependent
@pytest.mark.parametrize("run_cleanup", [[PYTEST_WOKE_PATH]], indirect=True)
async def test_file_executable(run_cleanup, config):
    svm = SolcVersionManager(config)
    await svm.install("0.8.10")
    output = subprocess.check_output([str(svm.get_path("0.8.10")), "--version"])
    assert b"0.8.10" in output

    oldest_version = svm.list_all()[0]
    await svm.install(oldest_version)
    output = subprocess.check_output([str(svm.get_path(oldest_version)), "--version"])
    assert str(oldest_version).encode("utf-8") in output
