from typing import Optional, Union, Dict, List, Set
from abc import ABC, abstractmethod
from pathlib import Path
import platform
import hashlib
import urllib.request
import urllib.error

from pydantic import BaseModel, Field
import aiohttp

from woke.a_config import WokeConfig, UnsupportedPlatformError


class ChecksumError(Exception):
    """
    Checksum of a downloaded file did not match the expected value.
    """


class SolcBuildInfo(BaseModel):
    path: str
    version: str
    build: str
    long_version: str = Field(alias="longVersion")
    keccak256: str
    sha256: str
    urls: List[str]


class SolcBuilds(BaseModel):
    builds: List[SolcBuildInfo]
    releases: Dict[str, str]
    latest_release: str = Field(alias="latestRelease")


class CompilerVersionManagerAbc(ABC):
    """
    ABC for all compiler version managers.
    """

    @abstractmethod
    def install(self, version: str, force_reinstall: bool = False) -> None:
        """
        Install the target compiler version.
        :param version: compiler version to be installed
        :param force_reinstall: if True, download target compiler version even if already installed
        """

    @abstractmethod
    def remove(self, version: str) -> None:
        """
        Remove the target compiler version.
        :param version: compiler version to be removed
        """

    @abstractmethod
    def get_path(self, version: str) -> Path:
        """
        Return a system path of the target compiler version executable.
        :param version: version of the compiler executable whose path is returned
        """

    @abstractmethod
    def list_all(self) -> Set[str]:
        """
        Return a set of all supported compiler versions.
        :return set of all supported compiler versions
        """

    def list_installed(self) -> Set[str]:
        """
        Return a set of installed compiler versions.
        :return: set of installed compiler versions
        """
        installed = set()
        for version in self.list_all():
            if self.get_path(version).is_file():
                installed.add(version)
        return installed


class SolcVersionManager(CompilerVersionManagerAbc):
    """
    Solc version manager that can install, remove and provide info about `solc` compiler.
    """

    # TODO: Add checks for minimal solc version into svm module
    # assignees: michprev

    # TODO: Add support for older solc versions in svm module
    #  Currently only builds present in binaries.soliditylang.org repository are supported.
    #  We should also support older solc releases.
    # assignees: michprev

    BINARIES_URL: str = "https://binaries.soliditylang.org"

    __platform: str
    __solc_list_url: str
    __compilers_path: Path
    __solc_list_path: Path
    __solc_builds: Optional[SolcBuilds]

    def __init__(self, woke_config: WokeConfig):
        system = platform.system()
        if system == "Linux":
            self.__platform = "linux-amd64"
        elif system == "Darwin":
            self.__platform = "macosx-amd64"
        elif system == "Windows":
            self.__platform = "windows-amd64"
        else:
            raise UnsupportedPlatformError(f"Platform '{system}' is not supported.")

        self.__solc_list_url = f"{self.BINARIES_URL}/{self.__platform}/list.json"
        self.__compilers_path = woke_config.woke_root_path / "compilers"
        self.__solc_list_path = self.__compilers_path / "solc.json"
        self.__solc_builds = None

        self.__compilers_path.mkdir(parents=True, exist_ok=True)

    async def install(self, version: str, force_reinstall: bool = False) -> None:
        self.__fetch_list_file()
        if self.__solc_builds is None:
            raise RuntimeError(
                f"Unable to fetch or correctly parse {self.__solc_list_url}."
            )

        if self.get_path(version).is_file() and not force_reinstall:
            return
        if version not in self.__solc_builds.releases:
            raise ValueError(f"solc version '{version}' does not exist.")

        filename = self.__solc_builds.releases[version]
        build_info = next(b for b in self.__solc_builds.builds if b.version == version)
        download_url = f"{self.BINARIES_URL}/{self.__platform}/{filename}"
        local_path = self.__compilers_path / filename

        async with aiohttp.ClientSession() as session:
            async with session.get(download_url) as r:
                with local_path.open("wb") as f:
                    async for chunk in r.content.iter_chunked(8 * 1024):
                        f.write(chunk)

        # TODO: Implement keccak256 checksum verifying in svm module
        # assignees: michprev
        sha256 = build_info.sha256
        if sha256.startswith("0x"):
            sha256 = sha256[2:]

        if not self.__verify_sha256(local_path, sha256):
            local_path.unlink()
            raise ChecksumError(
                f"Failed to verify SHA256 checksum of '{filename}' file."
            )

        local_path.chmod(0o775)

    def remove(self, version: str) -> None:
        path = self.get_path(version)
        if path.is_file():
            path.unlink()
        else:
            raise ValueError(
                f"solc version '{version}' was not installed - cannot remove."
            )

    def get_path(self, version: str) -> Path:
        self.__fetch_list_file()
        if self.__solc_builds is None:
            raise RuntimeError(
                f"Unable to fetch or correctly parse {self.__solc_list_url}."
            )

        if version not in self.__solc_builds.releases:
            raise ValueError(f"solc version '{version}' does not exist")

        return self.__compilers_path / self.__solc_builds.releases[version]

    def list_all(self) -> Set[str]:
        self.__fetch_list_file()
        if self.__solc_builds is None:
            raise RuntimeError(
                f"Unable to fetch or correctly parse {self.__solc_list_url}."
            )

        return set(self.__solc_builds.releases.keys())

    def __fetch_list_file(self) -> None:
        """
        Download ``list.json`` file from `binaries.soliditylang.org <binaries.soliditylang.org>`_ for the current
        platform and save it as ``{woke_root_path}/compilers/solc.json``. In case of network issues, try to
        use the locally downloaded solc builds file as a fallback.
        """
        if self.__solc_builds is not None:
            return

        try:
            with urllib.request.urlopen(self.__solc_list_url) as response:
                json = response.read()
                self.__solc_builds = SolcBuilds.parse_raw(json)
                self.__solc_list_path.write_bytes(json)
        except urllib.error.URLError:
            # in case of networking issues try to use the locally downloaded solc builds file as a fallback
            if self.__solc_list_path.is_file():
                self.__solc_builds = SolcBuilds.parse_file(self.__solc_list_path)
            else:
                raise

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
