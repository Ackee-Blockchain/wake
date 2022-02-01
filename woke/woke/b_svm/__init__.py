from typing import Optional, Union, Dict, List, Set
from abc import ABC, abstractmethod
from pathlib import Path
import platform
import hashlib

from pydantic import BaseModel, Field
import requests


class UnsupportedPlatformError(Exception):
    pass


class ChecksumError(Exception):
    pass


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
    @abstractmethod
    def install(self, version: str, force_reinstall: bool = False) -> None:
        pass

    @abstractmethod
    def remove(self, version: str) -> None:
        pass

    @abstractmethod
    def get_path(self, version: str) -> Path:
        pass

    @abstractmethod
    def list_all(self) -> Set[str]:
        pass

    def list_installed(self) -> Set[str]:
        installed = set()
        for version in self.list_all():
            if self.get_path(version).is_file():
                installed.add(version)
        return installed


class SolcVersionManager(CompilerVersionManagerAbc):
    BINARIES_URL: str = "https://binaries.soliditylang.org"

    __platform: str
    __solc_list_url: str
    __compilers_path: Path
    __solc_list_path: Path
    __solc_builds: Optional[SolcBuilds]

    def __init__(self, *_, woke_root_path: Optional[Union[str, Path]] = None):
        system = platform.system()
        if system == "Linux":
            self.__platform = "linux-amd64"
            default_root_path = Path.home() / ".woke"
        elif system == "Darwin":
            self.__platform = "macosx-amd64"
            default_root_path = Path.home() / ".woke"
        elif system == "Windows":
            self.__platform = "windows-amd64"
            default_root_path = Path.home() / "Woke"
        else:
            raise UnsupportedPlatformError(f"Platform '{system}' is not supported.")

        if woke_root_path is None:
            woke_root_path = default_root_path

        self.__solc_list_url = f"{self.BINARIES_URL}/{self.__platform}/list.json"
        self.__compilers_path = Path(woke_root_path) / "compilers"
        self.__solc_list_path = self.__compilers_path / "list.json"
        self.__solc_builds = None

        self.__compilers_path.mkdir(parents=True, exist_ok=True)

    def install(self, version: str, force_reinstall: bool = False) -> None:
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

        with requests.get(download_url, stream=True) as r:
            r.raise_for_status()
            with local_path.open("wb") as f:
                for chunk in r.iter_content(8 * 1024):
                    f.write(chunk)

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
        if self.__solc_builds is not None:
            return

        response = requests.get(self.__solc_list_url)
        self.__solc_builds = SolcBuilds.parse_raw(response.text)
        self.__solc_list_path.write_text(response.text, encoding="utf-8")

    def __verify_sha256(self, path: Path, expected: str) -> bool:
        h = hashlib.sha256()
        with path.open("rb") as f:
            while True:
                chunk = f.read(4 * 1024)
                if not chunk:
                    break
                h.update(chunk)

        return h.hexdigest() == expected
