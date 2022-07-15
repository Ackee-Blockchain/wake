import asyncio
import subprocess
from pathlib import Path, PurePath
from typing import Dict

from woke.config import WokeConfig
from woke.core.solidity_version import SolidityVersion
from woke.svm import SolcVersionManager

from .exceptions import SolcCompilationError
from .input_data_model import (
    SolcInput,
    SolcInputLanguageEnum,
    SolcInputSettings,
    SolcInputSource,
)
from .output_data_model import SolcOutput


class SolcFrontend:
    __config: WokeConfig
    __svm: SolcVersionManager

    def __init__(self, woke_config: WokeConfig):
        self.__config = woke_config
        self.__svm = SolcVersionManager(woke_config)

    async def compile(
        self,
        files: Dict[PurePath, Path],
        sources: Dict[PurePath, str],
        target_version: SolidityVersion,
        settings: SolcInputSettings,
    ) -> SolcOutput:
        standard_input = SolcInput(language=SolcInputLanguageEnum.SOLIDITY)

        for unit_name, path in files.items():
            if target_version >= "0.8.8":
                # path = {include_path} / {unit_name}
                # since 0.8.8 include paths can be passed as cmdline arguments to solc
                # because of this, source unit names can be passed here instead of (full) absolute paths
                standard_input.sources[
                    str(unit_name).replace("\\", "/")
                ] = SolcInputSource(urls=[str(unit_name)])
            else:
                # for solc versions < 0.8.8 include paths cannot be passed as cmdline arguments to solc
                # because of this, absolute paths must be used here
                standard_input.sources[
                    str(unit_name).replace("\\", "/")
                ] = SolcInputSource(urls=[str(path)])

        for unit_name, content in sources.items():
            standard_input.sources[str(unit_name).replace("\\", "/")] = SolcInputSource(
                content=content
            )
        standard_input.settings = settings

        return await self.__run_solc(target_version, standard_input)

    async def __run_solc(
        self, target_version: SolidityVersion, standard_input: SolcInput
    ) -> SolcOutput:
        path = self.__svm.get_path(target_version)
        if not path.is_file():
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

        # the first argument in this call cannot be `Path` because of https://bugs.python.org/issue35246
        proc = await asyncio.create_subprocess_exec(
            *args,
            cwd=self.__config.project_root_path,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        standard_input_json = standard_input.json(by_alias=True, exclude_none=True)
        out, err = await proc.communicate(standard_input_json.encode("utf-8"))
        if proc.returncode != 0:
            raise SolcCompilationError(err)

        return SolcOutput.parse_raw(out)
