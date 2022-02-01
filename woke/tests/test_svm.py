from pathlib import Path
from typing import Optional, List, Union
import shutil
import subprocess

import pytest

from woke.b_svm import SolcVersionManager


PYTEST_WOKE_PATH = Path.home() / ".tmpwoke_KVUhSovO5J"
PYTEST_WOKE_PATH2 = Path.home() / ".tmpwoke2_fLtqXkHeVH"


@pytest.fixture()
def run_cleanup(request):
    yield

    paths: Optional[List[Union[str, Path]]] = request.param
    if paths is not None:
        for path in paths:
            shutil.rmtree(path, True)


@pytest.mark.parametrize("run_cleanup", [[PYTEST_WOKE_PATH]], indirect=True)
def test_basic_usage(run_cleanup):
    svm = SolcVersionManager(woke_root_path=PYTEST_WOKE_PATH)

    assert len(svm.list_installed()) == 0
    assert "0.8.10" in svm.list_all()
    svm.install("0.8.10")
    assert "0.8.10" in svm.list_installed()
    svm.remove("0.8.10")
    assert len(svm.list_installed()) == 0


@pytest.mark.parametrize("run_cleanup", [[PYTEST_WOKE_PATH]], indirect=True)
def test_install_invalid_version(run_cleanup):
    svm = SolcVersionManager(woke_root_path=PYTEST_WOKE_PATH)
    with pytest.raises(ValueError):
        svm.install("0.8.a")
    assert len(svm.list_installed()) == 0


@pytest.mark.parametrize(
    "run_cleanup", [[PYTEST_WOKE_PATH, PYTEST_WOKE_PATH2]], indirect=True
)
def test_two_woke_root_paths(run_cleanup):
    svm1 = SolcVersionManager(woke_root_path=PYTEST_WOKE_PATH)
    svm2 = SolcVersionManager(woke_root_path=str(PYTEST_WOKE_PATH2))

    assert "0.8.10" in svm1.list_all()
    assert "0.8.9" in svm2.list_all()
    assert len(svm1.list_installed()) == 0
    assert len(svm2.list_installed()) == 0
    svm1.install("0.8.10")
    svm2.install("0.8.9")
    assert "0.8.10" in svm1.list_installed()
    assert "0.8.9" not in svm1.list_installed()
    assert "0.8.9" in svm2.list_installed()
    assert "0.8.10" not in svm2.list_installed()


@pytest.mark.parametrize("run_cleanup", [[PYTEST_WOKE_PATH]], indirect=True)
def test_remove_not_installed_version(run_cleanup):
    svm = SolcVersionManager(woke_root_path=PYTEST_WOKE_PATH)
    with pytest.raises(ValueError):
        svm.remove("0.8.10")


@pytest.mark.parametrize("run_cleanup", [[PYTEST_WOKE_PATH]], indirect=True)
def test_file_executable(run_cleanup):
    svm = SolcVersionManager(woke_root_path=PYTEST_WOKE_PATH)
    svm.install("0.8.10")

    output = subprocess.check_output([svm.get_path("0.8.10"), "--version"])
    assert b"0.8.10" in output
