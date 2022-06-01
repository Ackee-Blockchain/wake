from typing import Optional

from woke.a_config import WokeConfig
from .enums import TraceValueEnum
from .lsp_compiler import LspCompiler


class LspContext:
    __compiler: LspCompiler
    __config: WokeConfig

    shutdown_received: bool
    initialized: bool
    trace_value: TraceValueEnum

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


    """
    def update_workspace(self,
                        document_uri: DocumentUri,
                        document_veriosn: int, 
                        document_change: TextDocumentContentChangeEvent):
        old_doc = self.workspace[document_uri]
        if document_change.range is None:
            self.workspace[document_uri].text = document_change.text
        else:
            change_from = document_change.range.start
            change_to = document_change.range.end
            self.workspace[document_uri].text[]
    """
