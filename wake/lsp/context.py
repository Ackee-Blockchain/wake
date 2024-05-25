from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from ..config import WakeConfig
from ..core.solidity_version import SemanticVersion
from ..utils.openzeppelin import get_contracts_package_version
from .features.diagnostic import diagnostics_loop
from .lsp_compiler import LspCompiler
from .lsp_parser import LspParser

if TYPE_CHECKING:
    from .server import LspServer


class LspContext:
    __server: LspServer
    __workspace_config: WakeConfig
    __compiler: LspCompiler
    __diagnostics_queue: asyncio.Queue
    __parser: LspParser

    use_toml: bool
    toml_path: Path

    def __init__(
        self, server: LspServer, config: WakeConfig, perform_files_discovery: bool
    ) -> None:
        self.__server = server
        self.__workspace_config = config
        self.__diagnostics_queue = asyncio.Queue()
        self.__compiler = LspCompiler(
            server,
            self.__diagnostics_queue,
            perform_files_discovery,
        )
        self.__parser = LspParser(server)

    def run(self) -> None:
        self.__server.create_task(diagnostics_loop(self.__server, self))
        self.__server.create_task(self.__compiler.run(self.__workspace_config))

    @property
    def config(self) -> WakeConfig:
        return self.__workspace_config

    @property
    def compiler(self) -> LspCompiler:
        return self.__compiler

    @property
    def diagnostics_queue(self) -> asyncio.Queue:
        return self.__diagnostics_queue

    @property
    def server(self) -> LspServer:
        return self.__server

    @property
    def parser(self) -> LspParser:
        return self.__parser
