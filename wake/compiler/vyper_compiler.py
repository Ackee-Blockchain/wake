import logging
from pathlib import Path
from typing import Iterable, Dict, Optional

import rich.console
from vvm import compile_standard, get_installable_vyper_versions, set_vyper_version, install_vyper

from wake.config import WakeConfig
from wake.core.logging import get_logger
from wake.core.solidity_version import SolidityVersion
from wake.regex_parser.vyper_parser import VyperSourceParser, VyperVersionRanges, VyperVersionRange

logger = get_logger(__name__)
logger.setLevel(logging.DEBUG)


class VyperCompiler:
    _config: WakeConfig
    _parser: VyperSourceParser

    def __init__(self, config: WakeConfig):
        self._config = config
        self._parser = VyperSourceParser()

    def gen_input(self, files: Iterable[Path]) -> Dict:
        return {
            "language": "Vyper",
            "sources": {
                str(p): {"content": p.read_text()} for p in files
            },
            "settings": {
                "outputSelection": {
                    "*": [
                        "abi",
                        "ast",
                        "evm.bytecode",
                        "evm.deployedBytecode",
                    ]
                },
            }
        }

    def compile(self, files: Iterable[Path]):
        contents: Dict[Path, bytes] = {p: p.read_bytes() for p in files}
        versions = VyperVersionRanges([VyperVersionRange("0.0.0", True, None, None)])
        for content in contents.values():
            versions &= self._parser.parse(content)

        installable = get_installable_vyper_versions()
        target_version = None

        for v in installable:
            if v.is_devrelease or v.is_postrelease or v.is_prerelease:
                continue

            vv = SolidityVersion.fromstring(str(v))
            if vv in versions:
                target_version = vv
                install_vyper(v, show_progress=True)
                set_vyper_version(v)
                break

        if target_version is None:
            raise Exception("No suitable version found")
        if target_version < self._config.min_vyper_version or target_version > self._config.max_vyper_version:
            raise Exception("No suitable version found")

        logger.debug(f"Compiling to {target_version}")

        ret = compile_standard(self.gen_input(files), base_path=str(Path.cwd()))

        logger.debug(ret)
        return ret
