from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Optional

from ..config import WokeConfig
from ..core.solidity_version import SemanticVersion
from ..utils.openzeppelin import get_contracts_package_version
from .features.diagnostic import diagnostics_loop
from .lsp_compiler import LspCompiler

if TYPE_CHECKING:
    from .server import LspServer


class LspContext:
    __server: LspServer
    __workspace_config: WokeConfig
    __compiler: LspCompiler
    __diagnostics_queue: asyncio.Queue
    __openzeppelin_contracts_version: Optional[SemanticVersion]

    def __init__(
        self, server: LspServer, config: WokeConfig, perform_files_discovery: bool
    ) -> None:
        self.__server = server
        self.__workspace_config = config
        self.__diagnostics_queue = asyncio.Queue()
        self.__compiler = LspCompiler(
            server, self.__diagnostics_queue, perform_files_discovery
        )
        self.__openzeppelin_contracts_version = get_contracts_package_version(config)

    def run(self) -> None:
        self.__server.create_task(diagnostics_loop(self.__server, self))
        self.__server.create_task(self.__compiler.run(self.__workspace_config))

    @property
    def config(self) -> WokeConfig:
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
    def openzeppelin_contracts_version(self) -> Optional[SemanticVersion]:
        return self.__openzeppelin_contracts_version
