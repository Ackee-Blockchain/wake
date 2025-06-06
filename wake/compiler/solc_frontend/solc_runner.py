import asyncio
import logging
import platform
import subprocess
from pathlib import Path
from typing import Dict

from wake.config import WakeConfig
from wake.core import get_logger
from wake.core.enums import EvmVersionEnum
from wake.core.solidity_version import SolidityVersion
from wake.svm import SolcVersionManager

from .exceptions import SolcCompilationError
from .input_data_model import (
    SolcInput,
    SolcInputLanguageEnum,
    SolcInputSettings,
    SolcInputSource,
)
from .output_data_model import SolcOutput

logger = get_logger(__name__)


MAX_SUPPORTED_EVM_VERSIONS = {
    # older solc versions are not supported anyway
    SolidityVersion.fromstring("0.5.12"): EvmVersionEnum.BERLIN,
    SolidityVersion.fromstring("0.8.7"): EvmVersionEnum.LONDON,
    SolidityVersion.fromstring("0.8.18"): EvmVersionEnum.PARIS,
    SolidityVersion.fromstring("0.8.20"): EvmVersionEnum.SHANGHAI,
    SolidityVersion.fromstring("0.8.24"): EvmVersionEnum.CANCUN,
    SolidityVersion.fromstring("0.8.27"): EvmVersionEnum.PRAGUE,
    SolidityVersion.fromstring("0.8.29"): EvmVersionEnum.OSAKA,
}


class SolcFrontend:
    __config: WakeConfig
    __svm: SolcVersionManager

    def __init__(self, wake_config: WakeConfig):
        self.__config = wake_config
        self.__svm = SolcVersionManager(wake_config)

    async def compile(
        self,
        files: Dict[str, Path],
        sources: Dict[str, str],
        target_version: SolidityVersion,
        settings: SolcInputSettings,
    ) -> SolcOutput:
        standard_input = SolcInput(language=SolcInputLanguageEnum.SOLIDITY)

        for unit_name, path in files.items():
            if target_version >= "0.8.8":
                # path = {include_path} / {unit_name}
                # since 0.8.8 include paths can be passed as cmdline arguments to solc
                # because of this, source unit names can be passed here instead of (full) absolute paths
                standard_input.sources[unit_name] = SolcInputSource(urls=[unit_name])
            else:
                # for solc versions < 0.8.8 include paths cannot be passed as cmdline arguments to solc
                # because of this, absolute paths must be used here
                standard_input.sources[unit_name] = SolcInputSource(urls=[str(path)])

        for unit_name, content in sources.items():
            standard_input.sources[unit_name] = SolcInputSource(content=content)
        standard_input.settings = settings.model_copy(deep=True)

        if (
            target_version < "0.8.18"
            and settings.metadata is not None
            and settings.metadata.append_CBOR is not None
        ):
            if not settings.metadata.append_CBOR:
                logger.warning(
                    "`append_CBOR` is not supported for solc versions < 0.8.18. This option will be ignored."
                )
            standard_input.settings.metadata = settings.metadata.model_copy(
                update={"append_CBOR": None}
            )

        if settings.evm_version is not None:
            # find nearest <= version in MAX_SUPPORTED_EVM_VERSIONS
            nearest_version = max(
                version
                for version in MAX_SUPPORTED_EVM_VERSIONS.keys()
                if version <= target_version
            )

            if MAX_SUPPORTED_EVM_VERSIONS[nearest_version] < settings.evm_version:
                logger.warning(
                    f"solc version `{target_version}` does not support evm version `{settings.evm_version}` set in settings. "
                    f"Lowering evm version to `{MAX_SUPPORTED_EVM_VERSIONS[nearest_version]}`."
                )
                standard_input.settings.evm_version = MAX_SUPPORTED_EVM_VERSIONS[
                    nearest_version
                ]

        return await self.__run_solc(target_version, standard_input)

    async def __run_solc(
        self, target_version: SolidityVersion, standard_input: SolcInput
    ) -> SolcOutput:
        path = self.__svm.get_path(target_version)
        if not self.__svm.installed(target_version):
            raise SolcCompilationError(
                f"solc version `{target_version}` is not installed."
            )
        args = [str(path.resolve()), "--standard-json"]

        allow_paths = ",".join(
            str(path) for path in self.__config.compiler.solc.allow_paths
        )
        args.append(f"--allow-paths=.,{allow_paths}")

        if target_version >= "0.8.8":
            args.append("--base-path=.")
            for include_path in self.__config.compiler.solc.include_paths:
                args.append(f"--include-path={include_path}")
            args.append(f"--include-path={self.__config.wake_contracts_path}")

        logger.debug(f"Running solc: {' '.join(args)}")

        # the first argument in this call cannot be `Path` because of https://bugs.python.org/issue35246
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                cwd=self.__config.project_root_path,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except OSError as e:
            if (
                e.errno == 86
                and platform.system() == "Darwin"
                and platform.machine() in {"aarch64", "arm64", "AARCH64", "ARM64"}
            ):
                raise RuntimeError(
                    "Rosetta 2 must be installed to run Solidity compiler on Apple Silicon. Run `softwareupdate --install-rosetta` to install it."
                )
            raise

        standard_input_json = standard_input.model_dump_json(
            by_alias=True, exclude_none=True
        )
        logger.debug(f"solc input: {standard_input_json}")

        out, err = await proc.communicate(standard_input_json.encode("utf-8"))
        if proc.returncode != 0:
            raise SolcCompilationError(err)

        return SolcOutput.model_validate_json(out)
