from woke.a_config import WokeConfig
from .enums import TraceValueEnum
from .basic_structures import *


class LSPContext:
    woke_config: Optional[WokeConfig]
    shutdown_received: bool
    initialized: bool
    trace_value: TraceValueEnum
    client_capabilities: List[str]
    # workspace: Union[dict, None]

    def __init__(self) -> None:
        self.woke_config = None
        self.shutdown_received = False
        self.initialized = False
        self.trace_value = TraceValueEnum(TraceValueEnum.OFF)
        self.client_capabilities = []

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
