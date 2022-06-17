import re
import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from woke.cli.__main__ import main
from woke.config import WokeConfig
from woke.core.solidity_version import SolidityVersion
from woke.svm import SolcVersionManager

PYTEST_WOKE_ROOT_PATH = (Path.home() / ".tmpwoke_Z6yVySfqSk").resolve()


@pytest.fixture()
def woke_root_path():
    PYTEST_WOKE_ROOT_PATH.mkdir()
    yield
    shutil.rmtree(PYTEST_WOKE_ROOT_PATH, True)


@pytest.mark.slow
def test_svm_install(woke_root_path):
    config = WokeConfig(woke_root_path=PYTEST_WOKE_ROOT_PATH)
    config.load_configs()
    svm = SolcVersionManager(config)
    cli_runner = CliRunner()

    latest_version = next(reversed(svm.list_all()))
    cli_result = cli_runner.invoke(
        main, [f"--woke-root-path={PYTEST_WOKE_ROOT_PATH}", "svm", "install", "*"]
    )
    print(cli_result.output)
    assert cli_result.exit_code == 0
    assert latest_version in svm.list_installed()


@pytest.mark.slow
def test_svm_switch(woke_root_path):
    config = WokeConfig(woke_root_path=PYTEST_WOKE_ROOT_PATH)
    config.load_configs()
    svm = SolcVersionManager(config)
    cli_runner = CliRunner()

    cli_result = cli_runner.invoke(
        main, [f"--woke-root-path={PYTEST_WOKE_ROOT_PATH}", "svm", "switch", "0.6.2"]
    )
    assert cli_result.exit_code != 0
    cli_result = cli_runner.invoke(
        main, [f"--woke-root-path={PYTEST_WOKE_ROOT_PATH}", "svm", "install", "0.6.2"]
    )
    assert cli_result.exit_code == 0
    assert len(svm.list_installed()) == 1
    cli_result = cli_runner.invoke(
        main, [f"--woke-root-path={PYTEST_WOKE_ROOT_PATH}", "svm", "switch", "0.6.2"]
    )
    assert cli_result.exit_code == 0

    version_str = (PYTEST_WOKE_ROOT_PATH / ".woke_solc_version").read_text()
    version = SolidityVersion.fromstring(version_str)
    assert version in svm.list_installed()
    assert version == "0.6.2"


@pytest.mark.slow
def test_svm_use(woke_root_path):
    config = WokeConfig(woke_root_path=PYTEST_WOKE_ROOT_PATH)
    config.load_configs()
    svm = SolcVersionManager(config)
    cli_runner = CliRunner()

    cli_result = cli_runner.invoke(
        main, [f"--woke-root-path={PYTEST_WOKE_ROOT_PATH}", "svm", "use", "0.8.4"]
    )
    assert cli_result.exit_code == 0
    assert len(svm.list_installed()) == 1

    version_str = (PYTEST_WOKE_ROOT_PATH / ".woke_solc_version").read_text()
    version = SolidityVersion.fromstring(version_str)
    assert version in svm.list_installed()
    assert version == "0.8.4"


@pytest.mark.slow
def test_svm_list(woke_root_path):
    config = WokeConfig(woke_root_path=PYTEST_WOKE_ROOT_PATH)
    config.load_configs()
    cli_runner = CliRunner()

    cli_result = cli_runner.invoke(
        main, [f"--woke-root-path={PYTEST_WOKE_ROOT_PATH}", "svm", "install", "0.7.6"]
    )
    assert cli_result.exit_code == 0
    cli_result = cli_runner.invoke(
        main, [f"--woke-root-path={PYTEST_WOKE_ROOT_PATH}", "svm", "install", "0.8.0"]
    )
    assert cli_result.exit_code == 0
    cli_result = cli_runner.invoke(
        main, [f"--woke-root-path={PYTEST_WOKE_ROOT_PATH}", "svm", "list"]
    )
    assert cli_result.exit_code == 0

    assert re.search(r"^.*\s0\.7\.6\s*$", cli_result.output, re.MULTILINE)
    assert re.search(r"^.*\s0\.8\.0\s*$", cli_result.output, re.MULTILINE)


@pytest.mark.slow
def test_svm_list_all(woke_root_path):
    config = WokeConfig(woke_root_path=PYTEST_WOKE_ROOT_PATH)
    config.load_configs()
    cli_runner = CliRunner()

    cli_result = cli_runner.invoke(
        main, [f"--woke-root-path={PYTEST_WOKE_ROOT_PATH}", "svm", "install", "0.4.20"]
    )
    assert cli_result.exit_code == 0
    cli_result = cli_runner.invoke(
        main, [f"--woke-root-path={PYTEST_WOKE_ROOT_PATH}", "svm", "install", "0.6.3"]
    )
    assert cli_result.exit_code == 0
    cli_result = cli_runner.invoke(
        main, [f"--woke-root-path={PYTEST_WOKE_ROOT_PATH}", "svm", "list", "--all"]
    )
    assert cli_result.exit_code == 0

    assert re.search(r"^.*\s0\.4\.19\s*$", cli_result.output, re.MULTILINE)
    assert re.search(r"^.*\s0\.4\.20\s.*installed.*$", cli_result.output, re.MULTILINE)
    assert re.search(r"^.*\s0\.5\.4\s*$", cli_result.output, re.MULTILINE)
    assert re.search(r"^.*\s0\.6\.3\s.*installed.*$", cli_result.output, re.MULTILINE)
    assert re.search(r"^.*\s0\.8\.12\s*$", cli_result.output, re.MULTILINE)


@pytest.mark.slow
def test_svm_remove(woke_root_path):
    config = WokeConfig(woke_root_path=PYTEST_WOKE_ROOT_PATH)
    config.load_configs()
    svm = SolcVersionManager(config)
    cli_runner = CliRunner()

    cli_result = cli_runner.invoke(
        main, [f"--woke-root-path={PYTEST_WOKE_ROOT_PATH}", "svm", "remove", "0.6.5"]
    )
    assert cli_result.exit_code != 0
    cli_result = cli_runner.invoke(
        main,
        [
            f"--woke-root-path={PYTEST_WOKE_ROOT_PATH}",
            "svm",
            "remove",
            "0.6.5",
            "--ignore-missing",
        ],
    )
    assert cli_result.exit_code == 0
    cli_result = cli_runner.invoke(
        main, [f"--woke-root-path={PYTEST_WOKE_ROOT_PATH}", "svm", "install", "0.6.3"]
    )
    assert cli_result.exit_code == 0
    assert "0.6.3" in svm.list_installed()
    cli_result = cli_runner.invoke(
        main, [f"--woke-root-path={PYTEST_WOKE_ROOT_PATH}", "svm", "remove", "0.6.3"]
    )
    assert cli_result.exit_code == 0
    assert len(svm.list_installed()) == 0
    assert not svm.get_path("0.6.3").parent.is_dir()
