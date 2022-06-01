import queue
import logging
import re
from pathlib import Path
from threading import Thread
from typing import Dict, List
from urllib.parse import urlparse

from woke.a_config import WokeConfig
from woke.l_lsp.basic_structures import DidOpenTextDocumentParams, DidChangeTextDocumentParams

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


ENCODING = "utf-16-le"


class LspCompiler:
    __config: WokeConfig
    __thread: Thread
    __file_changes_queue: queue.Queue

    # accessed from the compilation thread
    # full path -> contents
    __files: Dict[Path, str]

    def __init__(self, config: WokeConfig):
        self.__config = config
        self.__file_changes_queue = queue.Queue()
        self.__files = dict()

    def run(self):
        self.__thread = Thread(target=self.__compilation_loop, args=())
        self.__thread.start()

    @property
    def file_changes_queue(self) -> queue.Queue:
        return self.__file_changes_queue

    @staticmethod
    def __uri_to_path(uri: str) -> Path:
        p = urlparse(uri)
        return Path(p.path)

    def __compilation_loop(self):
        # perform Solidity files discovery
        project_path = self.__config.project_root_path

        for file in project_path.rglob("*.sol"):
            if file.is_file():
                self.__files[file.resolve()] = file.read_text()

        while True:
            while not self.file_changes_queue.empty():
                change = self.file_changes_queue.get()

                if isinstance(change, DidOpenTextDocumentParams):
                    path = self.__uri_to_path(change.text_document.uri).resolve()
                    self.__files[path] = change.text_document.text
                elif isinstance(change, DidChangeTextDocumentParams):
                    path = self.__uri_to_path(change.text_document.uri).resolve()

                    for content_change in change.content_changes:
                        start = content_change.range.start
                        end = content_change.range.end

                        # str.splitlines() removes empty lines => cannot be used
                        # str.split() removes separators => cannot be used
                        tmp_lines = re.split(r"(\r?\n)", self.__files[path])
                        tmp_lines2: List[str] = []
                        for line in tmp_lines:
                            if line in {"\r\n", "\n"}:
                                tmp_lines2[-1] += line
                            else:
                                tmp_lines2.append(line)

                        lines: List[bytearray] = [bytearray(line.encode(ENCODING)) for line in tmp_lines2]

                        if start.line == end.line:
                            line = lines[start.line]
                            line[start.character*2:end.character*2] = b""
                            line[start.character*2:start.character*2] = content_change.text.encode(ENCODING)
                        else:
                            start_line = lines[start.line]
                            end_line = lines[end.line]
                            start_line[start.character*2:] = b""
                            end_line[:end.character*2] = b""

                            for i in range(start.line+1, end.line):
                                lines[i] = bytearray(b"")

                        self.__files[path] = "".join(line.decode(ENCODING) for line in lines)
                else:
                    raise Exception("Unknown change type")

            # run the compilation
            pass
