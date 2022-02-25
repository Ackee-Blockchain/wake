from typing import AnyStr, Dict
from pathlib import Path
import subprocess
import asyncio

from woke.a_config import WokeConfig
from woke.b_svm import SolcVersionManager
from woke.c_regex_parsing import SolidityVersion
from .input_data_model import SolcInput, SolcInputSource, SolcInputSettings
from .output_data_model import SolcOutput
from .exceptions import CompilationError


class SolcFrontend:
    __config: WokeConfig
    __svm: SolcVersionManager

    def __init__(self, woke_config: WokeConfig):
        self.__config = woke_config
        self.__svm = SolcVersionManager(woke_config)

    async def compile_src(
        self, solidity_src: AnyStr, target_version: SolidityVersion
    ) -> SolcOutput:
        raise NotImplementedError(
            "Direct source code compilation (instead of a list of files) is currently not implemented."
        )

    async def compile_files(
        self, files: Dict[str, Path], target_version: SolidityVersion
    ) -> SolcOutput:
        await self.__svm.install(target_version)

        standard_input = SolcInput()

        for unit_name, path in files.items():
            standard_input.sources[unit_name] = SolcInputSource(urls=[str(path)])
        standard_input.settings = SolcInputSettings()  # type: ignore
        standard_input.settings.output_selection = {"*": {"": ["ast"]}}

        solc_path = self.__svm.get_path(str(target_version))
        return await self.__run_solc(solc_path, standard_input)

    async def __run_solc(self, path: Path, standard_input: SolcInput) -> SolcOutput:
        allow_paths = ",".join(
            str(path) for path in self.__config.compiler.solc.allow_paths
        )

        # the first argument in this call cannot be `Path` because of https://bugs.python.org/issue35246
        proc = await asyncio.create_subprocess_exec(
            str(path.resolve()),
            f"--standard-json",
            "--base-path=.",
            f"--allow-paths=.,{allow_paths}",
            cwd=self.__config.project_root_path,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        standard_input_json = standard_input.json(by_alias=True, exclude_unset=True)
        out, err = await proc.communicate(standard_input_json.encode("utf-8"))
        if proc.returncode != 0:
            raise CompilationError(err)

        return SolcOutput.parse_raw(out)
