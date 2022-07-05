from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from woke.config import WokeConfig

from .enums import TraceValueEnum
from .lsp_compiler import LspCompiler

if TYPE_CHECKING:
    from .server import LspServer


class LspContext:
    __compiler: LspCompiler
    __config: WokeConfig

    def __init__(
        self, config: WokeConfig, server: LspServer, diagnostics_queue: asyncio.Queue
    ) -> None:
        self.__config = config
        self.__compiler = LspCompiler(self.__config, server, diagnostics_queue)

        self.shutdown_received = False
        self.initialized = False
        self.trace_value = TraceValueEnum(TraceValueEnum.OFF)

    @property
    def compiler(self) -> LspCompiler:
        return self.__compiler

    @property
    def config(self) -> WokeConfig:
        return self.__config
