from typing import Optional

from woke.config import WokeConfig

from .enums import TraceValueEnum
from .lsp_compiler import LspCompiler


class LspContext:
    __compiler: LspCompiler
    __config: WokeConfig

    def __init__(self, config: WokeConfig) -> None:
        self.__config = config
        self.__compiler = LspCompiler(self.__config)

        self.shutdown_received = False
        self.initialized = False
        self.trace_value = TraceValueEnum(TraceValueEnum.OFF)

    def create_compilation_thread(self) -> None:
        self.__compiler.run()

    @property
    def compiler(self) -> LspCompiler:
        return self.__compiler

    @property
    def config(self) -> WokeConfig:
        return self.__config
