from abc import ABC, abstractmethod
from pathlib import Path
from typing import Tuple, Union

from wake.core.solidity_version import VersionAbc


class CompilerVersionManagerAbc(ABC):
    """
    ABC for all compiler version managers.
    """

    @abstractmethod
    def installed(self, version: Union[VersionAbc, str]) -> bool:
        """
        Check if a compiler version is installed.
        :param version: compiler version to check
        :return: True if installed, False otherwise
        """

    @abstractmethod
    async def install(
        self, version: Union[VersionAbc, str], force_reinstall: bool = False
    ) -> None:
        """
        Install the target compiler version.
        :param version: compiler version to be installed
        :param force_reinstall: if True, download target compiler version even if already installed
        """

    @abstractmethod
    def remove(self, version: Union[VersionAbc, str]) -> None:
        """
        Remove the target compiler version.
        :param version: compiler version to be removed
        """

    @abstractmethod
    def get_path(self, version: Union[VersionAbc, str]) -> Path:
        """
        Return a system path of the target compiler version executable.
        :param version: version of the compiler executable whose path is returned
        """

    @abstractmethod
    def list_all(self) -> Tuple[VersionAbc]:
        """
        Return a set of all supported compiler versions.
        :return set of all supported compiler versions
        """

    def list_installed(self) -> Tuple[VersionAbc, ...]:
        """
        Return a set of installed compiler versions.
        :return: set of installed compiler versions
        """
        return tuple(version for version in self.list_all() if self.installed(version))
