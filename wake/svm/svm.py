import hashlib
import logging
import platform
import shutil
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple, Union
from zipfile import ZipFile

import aiohttp
from Crypto.Hash import keccak
from pydantic import BaseModel, Field, ValidationError

from wake.config import UnsupportedPlatformError, WakeConfig
from wake.core import get_logger
from wake.core.solidity_version import SolidityVersion

from .abc import CompilerVersionManagerAbc
from .exceptions import ChecksumError, UnsupportedVersionError

logger = get_logger(__name__)


class SolcBuildInfo(BaseModel):
    path: str
    version: SolidityVersion
    build: str
    long_version: SolidityVersion = Field(alias="longVersion")
    keccak256: str
    sha256: str
    urls: List[str]


class SolcBuilds(BaseModel):
    builds: List[SolcBuildInfo]
    releases: Dict[SolidityVersion, str]
    latest_release: str = Field(alias="latestRelease")


class SolcVersionManager(CompilerVersionManagerAbc):
    """
    Solc version manager that can install, remove and provide info about `solc` compiler.
    """

    # TODO: Add support for older solc versions in svm module
    #  Currently only builds present in binaries.soliditylang.org repository are supported.
    #  We should also support older solc releases.
    # assignees: michprev

    BINARIES_URL: str = "https://binaries.soliditylang.org"
    GITHUB_URL: str = "https://raw.githubusercontent.com/ethereum/solc-bin/gh-pages"
    INSTALL_RETRY_COUNT: int = 5

    __platform: str
    __solc_list_urls: List[str]
    __compilers_path: Path
    __solc_list_path: Path
    __solc_builds: Optional[SolcBuilds]
    __list_force_loaded: bool

    def __init__(self, wake_config: WakeConfig):
        system = platform.system()
        machine = platform.machine()
        amd64 = {"x86_64", "amd64", "AMD64", "x86-64"}
        arm64 = {"aarch64", "arm64", "AARCH64", "ARM64"}

        if system == "Linux" and machine in amd64:
            self.__platform = "linux-amd64"
        elif system == "Darwin" and machine in amd64.union(arm64):
            self.__platform = "macosx-amd64"
        elif system == "Windows" and machine in amd64.union(arm64):
            self.__platform = "windows-amd64"
        else:
            raise UnsupportedPlatformError(
                f"Solidity compiler binaries are not available for {system}-{machine}."
            )

        self.__solc_list_urls = [
            f"{self.BINARIES_URL}/{self.__platform}/list.json",
            f"{self.GITHUB_URL}/{self.__platform}/list.json",
        ]
        self.__compilers_path = wake_config.global_data_path / "compilers"
        self.__solc_list_path = self.__compilers_path / "solc.json"
        self.__solc_builds = None
        self.__list_force_loaded = False

        self.__compilers_path.mkdir(parents=True, exist_ok=True)

    def installed(self, version: Union[SolidityVersion, str]) -> bool:
        if isinstance(version, str):
            version = SolidityVersion.fromstring(version)

        self.__fetch_list_file(version, force=False)
        if self.__solc_builds is None:
            raise RuntimeError(
                f"Unable to fetch or correctly parse from '{self.__solc_list_urls}'."
            )

        path = self.get_path(version)
        if not path.is_file():
            return False

        if not self.__verify_checksums(version):
            return False
        return True

    async def install(
        self,
        version: Union[SolidityVersion, str],
        force_reinstall: bool = False,
        http_session: Optional[aiohttp.ClientSession] = None,
        progress: Optional[Callable[[int, int], Awaitable[None]]] = None,
    ) -> None:
        if isinstance(version, str):
            version = SolidityVersion.fromstring(version)

        self.__fetch_list_file(version, force=False)
        if self.__solc_builds is None:
            raise RuntimeError(
                f"Unable to fetch or correctly parse from '{self.__solc_list_urls}'."
            )

        minimal_version = self.list_all(force=False)[0]
        if version < minimal_version:
            raise UnsupportedVersionError(
                f"The minimal supported solc version for the current platform is `{minimal_version}`."
            )

        if version not in self.__solc_builds.releases:
            raise ValueError(f"solc version `{version}` does not exist.")

        filename = self.__solc_builds.releases[version]

        if self.get_path(version).is_file() and not force_reinstall:
            # cannot verify checksum for unzipped binaries
            if filename.endswith(".zip"):
                return
            # checksum verification passed
            if self.__verify_checksums(version):
                return

        local_path = self.get_path(version).parent / filename
        local_path.parent.mkdir(parents=True, exist_ok=True)

        for retry in range(self.INSTALL_RETRY_COUNT):
            download_url = (
                f"{self.BINARIES_URL}/{self.__platform}/{filename}"
                if retry % 2 == 0
                else f"{self.GITHUB_URL}/{self.__platform}/{filename}"
            )

            logger.debug(f"Downloading solc {version} from {download_url}")

            if http_session is None:
                async with aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=600)
                ) as session:
                    await self.__download_file(
                        download_url, local_path, session, progress
                    )
            else:
                await self.__download_file(
                    download_url, local_path, http_session, progress
                )

            if self.__verify_checksums(version):
                break
            elif retry == self.INSTALL_RETRY_COUNT - 1:
                local_path.unlink()
                raise ChecksumError(
                    f"Checksum of the downloaded solc version `{version}` does not match the expected value."
                )

        # unzip older Windows solc binary zipped together with DLLs
        if filename.endswith(".zip"):
            local_path = self.__unzip(local_path)

        local_path.chmod(0o775)

    def remove(self, version: Union[SolidityVersion, str]) -> None:
        path = self.get_path(version).parent
        if path.is_dir():
            shutil.rmtree(path)
        else:
            raise ValueError(
                f"solc version `{version}` was not installed - cannot remove."
            )

    def get_path(self, version: Union[SolidityVersion, str]) -> Path:
        if isinstance(version, str):
            version = SolidityVersion.fromstring(version)

        self.__fetch_list_file(version, force=False)
        if self.__solc_builds is None:
            raise RuntimeError(
                f"Unable to fetch or correctly parse from '{self.__solc_list_urls}'."
            )

        minimal_version = self.list_all(force=False)[0]
        if version < minimal_version:
            raise UnsupportedVersionError(
                f"The minimal supported solc version for the current platform is `{minimal_version}`."
            )

        if version not in self.__solc_builds.releases:
            raise ValueError(f"solc version `{version}` does not exist")

        filename = self.__solc_builds.releases[version]
        dirname = filename
        if dirname.endswith((".exe", ".zip")):
            dirname = dirname[:-4]
        if filename.endswith(".zip"):
            filename = filename[:-3] + "exe"
        return self.__compilers_path / dirname / filename

    def list_all(self, force: bool) -> Tuple[SolidityVersion, ...]:
        self.__fetch_list_file(None, force)
        if self.__solc_builds is None:
            raise RuntimeError(
                f"Unable to fetch or correctly parse from '{self.__solc_list_urls}'."
            )

        return tuple(sorted(self.__solc_builds.releases.keys()))

    async def __download_file(
        self,
        url: str,
        path: Path,
        http_session: aiohttp.ClientSession,
        progress: Optional[Callable[[int, int], Awaitable[None]]] = None,
    ) -> None:
        async with http_session.get(url) as r:
            total_size = r.headers.get("Content-Length")
            if total_size is not None:
                total_size = int(total_size)
            downloaded_size = 0
            with path.open("wb") as f:
                async for chunk in r.content.iter_chunked(8 * 1024):
                    f.write(chunk)
                    downloaded_size += len(chunk)
                    if total_size is not None and progress is not None:
                        await progress(downloaded_size, total_size)

    def __unzip(self, zip_path: Path) -> Path:
        """
        Unzip the Windows `solc` executable zip containing:
        - solc.exe - extract this file and rename it as `solc-windows-amd64-v{version}+commit.{commit}.exe`
        - soltest.exe - ignore this file (i.e. do not extract it)
        - extract any additional files (DLLs) next to the solc binary
        After that, delete the zip file.
        """
        base_path = zip_path.parent
        solc_filename = zip_path.name[:-3] + "exe"
        solc_path = zip_path.parent / solc_filename

        with ZipFile(zip_path, "r") as _zip:
            members = _zip.namelist()
            for member in members:
                if member == "soltest.exe":
                    # do not extract soltest.exe to save up the space
                    continue
                elif member == "solc.exe":
                    # rename solc.exe to the long name (containing version number, commit number etc.)
                    _zip.extract(member, base_path)
                    (base_path / "solc.exe").rename(solc_path)
                else:
                    # extract all the remaining files
                    _zip.extract(member, base_path)
        zip_path.unlink()
        return solc_path

    def __fetch_list_file(
        self, target_version: Optional[SolidityVersion], force: bool
    ) -> None:
        """
        Download ``list.json`` file from `binaries.soliditylang.org <binaries.soliditylang.org>`_ for the current
        platform and save it as ``{global_data_path}/compilers/solc.json``. In case of network issues, try to
        use the locally downloaded solc builds file as a fallback.
        """

        if self.__solc_builds is None and self.__solc_list_path.is_file() and not force:
            try:
                self.__solc_builds = SolcBuilds.model_validate_json(
                    self.__solc_list_path.read_text()
                )
            except ValidationError:
                pass

        if self.__solc_builds is not None and (
            target_version is not None
            and target_version in self.__solc_builds.releases
            or not force
            or self.__list_force_loaded
        ):
            return

        try:
            logger.debug(f"Downloading solc list from {self.__solc_list_urls[0]}")
            with urllib.request.urlopen(
                self.__solc_list_urls[0], timeout=0.5
            ) as response:
                json = response.read()
                self.__solc_builds = SolcBuilds.model_validate_json(json)
                self.__solc_list_path.write_bytes(json)
                self.__list_force_loaded = True
        except (urllib.error.URLError, OSError) as e:
            logger.warning(
                f"Failed to download solc list from {self.__solc_list_urls[0]}: {e}"
            )

            try:
                logger.debug(f"Downloading solc list from {self.__solc_list_urls[1]}")
                with urllib.request.urlopen(
                    self.__solc_list_urls[1], timeout=0.5
                ) as response:
                    json = response.read()
                    self.__solc_builds = SolcBuilds.model_validate_json(json)
                    self.__solc_list_path.write_bytes(json)
                    self.__list_force_loaded = True
            except (urllib.error.URLError, OSError) as e:
                logger.warning(
                    f"Failed to download solc list from {self.__solc_list_urls[1]}: {e}"
                )

                # in case of networking issues try to use the locally downloaded solc builds file as a fallback
                if self.__solc_list_path.is_file():
                    self.__solc_builds = SolcBuilds.model_validate_json(
                        self.__solc_list_path.read_text()
                    )
                else:
                    raise

    def __verify_checksums(self, version: SolidityVersion) -> bool:
        assert self.__solc_builds is not None
        build_info = next(b for b in self.__solc_builds.builds if b.version == version)
        local_path = self.get_path(version)

        filename = self.__solc_builds.releases[version]
        if filename.endswith(".zip"):
            local_path = local_path.parent / filename
            if not local_path.is_file():
                return True

        sha256 = build_info.sha256
        if sha256.startswith("0x"):
            sha256 = sha256[2:]

        keccak256 = build_info.keccak256
        if keccak256.startswith("0x"):
            keccak256 = keccak256[2:]

        if not self.__verify_sha256(local_path, sha256):
            return False
        if not self.__verify_keccak256(local_path, keccak256):
            return False
        return True

    def __verify_sha256(self, path: Path, expected: str) -> bool:
        """
        Check SHA256 checksum of the provided file against the expected value.
        :param path: path of the file whose checksum to be verified
        :param expected: expected value of SHA256 checksum
        :return: True if checksum matches the expected value, False otherwise
        """
        h = hashlib.sha256()
        with path.open("rb") as f:
            while True:
                chunk = f.read(4 * 1024)
                if not chunk:
                    break
                h.update(chunk)

        return h.hexdigest() == expected

    def __verify_keccak256(self, path: Path, expected: str) -> bool:
        """
        Check KECCAK256 checksum of the provided file against the expected value.
        :param path: path of the file whose checksum to be verified
        :param expected: expected value of KECCAK256 checksum
        :return: True if checksum matches the expected value, False otherwise
        """
        h = keccak.new(digest_bits=256)
        with path.open("rb") as f:
            while True:
                chunk = f.read(4 * 1024)
                if not chunk:
                    break
                h.update(chunk)

        return h.hexdigest() == expected
