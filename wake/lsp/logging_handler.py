import logging
from typing import List, Tuple

from wake.lsp.common_structures import MessageType


class LspLoggingHandler(logging.Handler):
    def __init__(self, buffer: List[Tuple[str, MessageType]]):
        super().__init__()
        self.buffer = buffer

    def emit(self, record: logging.LogRecord) -> None:
        log = f"{record.name}: {record.getMessage()}"

        if record.levelno >= logging.ERROR:
            self.buffer.append((log, MessageType.ERROR))
        elif record.levelno >= logging.WARNING:
            self.buffer.append((log, MessageType.WARNING))
        elif record.levelno >= logging.INFO:
            self.buffer.append((log, MessageType.INFO))
        else:
            self.buffer.append((log, MessageType.LOG))
