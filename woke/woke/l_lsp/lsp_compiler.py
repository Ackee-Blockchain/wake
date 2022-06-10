import asyncio
import queue
import logging
import re
import threading
from pathlib import Path
from threading import Thread
from typing import Dict, List, Set, Optional, Union
from urllib.parse import urlparse

from woke.a_config import WokeConfig
from woke.d_compile import SolcOutput, SolcOutputSelectionEnum
from woke.d_compile.compiler import SolidityCompiler
from woke.l_lsp.basic_structures import (
    DidOpenTextDocumentParams,
    DidChangeTextDocumentParams,
    DidCloseTextDocumentParams,
)

logger = logging.getLogger(__name__)


ENCODING = "utf-16-le"


class LspCompiler:
    __config: WokeConfig
    __thread: Thread
    __file_changes_queue: queue.Queue

    # accessed from the compilation thread
    # full path -> contents
    __files: Dict[Path, str]
    __opened_files: Set[Path]
    __modified_files: Set[Path]
    __compiler: SolidityCompiler
    __output: Optional[List[SolcOutput]]
    __output_contents: Dict[Path, str]

    output_ready: threading.Event

    def __init__(self, config: WokeConfig):
        self.__config = config
        self.__file_changes_queue = queue.Queue()
        self.__files = dict()
        self.__opened_files = set()
        self.__modified_files = set()
        self.__compiler = SolidityCompiler(config)
        self.__output = None
        self.__output_contents = dict()

        self.output_ready = threading.Event()

    def run(self):
        self.__thread = Thread(target=self.__compilation_loop, args=())
        self.__thread.start()

    @property
    def output(self) -> Optional[List[SolcOutput]]:
        return self.__output

    @staticmethod
    def uri_to_path(uri: str) -> Path:
        p = urlparse(uri)
        return Path(p.path)

    def add_change(
        self,
        change: Union[
            DidOpenTextDocumentParams,
            DidChangeTextDocumentParams,
            DidCloseTextDocumentParams,
        ],
    ) -> None:
        if not isinstance(change, DidCloseTextDocumentParams):
            self.output_ready.clear()
        self.__file_changes_queue.put(change)

    def get_file_content(self, file: Union[Path, str]) -> str:
        if isinstance(file, str):
            file = self.uri_to_path(file)
        return self.__output_contents[file]

    def __compilation_loop(self):
        # perform Solidity files discovery
        project_path = self.__config.project_root_path

        for file in (project_path / "contracts").rglob("*.sol"):
            if file.is_file():
                self.__files[file.resolve()] = file.read_text()

        # perform initial compilation
        out = asyncio.run(
            self.__compiler.compile(
                self.__files.keys(), [SolcOutputSelectionEnum.AST], False, False
            )
        )
        self.__output = list(out)
        self.__output_contents = self.__files.copy()
        self.output_ready.set()

        while True:
            while not self.__file_changes_queue.empty():
                change = self.__file_changes_queue.get()

                if isinstance(change, DidOpenTextDocumentParams):
                    path = self.uri_to_path(change.text_document.uri).resolve()
                    self.__files[path] = change.text_document.text
                    self.__opened_files.add(path)
                    self.__modified_files.add(path)
                elif isinstance(change, DidCloseTextDocumentParams):
                    path = self.uri_to_path(change.text_document.uri).resolve()
                    self.__opened_files.remove(path)
                elif isinstance(change, DidChangeTextDocumentParams):
                    path = self.uri_to_path(change.text_document.uri).resolve()
                    self.__modified_files.add(path)

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

                        lines: List[bytearray] = [
                            bytearray(line.encode(ENCODING)) for line in tmp_lines2
                        ]

                        if start.line == end.line:
                            line = lines[start.line]
                            line[start.character * 2 : end.character * 2] = b""
                            line[
                                start.character * 2 : start.character * 2
                            ] = content_change.text.encode(ENCODING)
                        else:
                            start_line = lines[start.line]
                            end_line = lines[end.line]
                            start_line[
                                start.character * 2 :
                            ] = content_change.text.encode(ENCODING)
                            end_line[: end.character * 2] = b""

                            for i in range(start.line + 1, end.line):
                                lines[i] = bytearray(b"")

                        self.__files[path] = "".join(
                            line.decode(ENCODING) for line in lines
                        )
                else:
                    raise Exception("Unknown change type")

            # run the compilation
            if len(self.__modified_files) > 0:
                modified_files = {
                    path: self.__files[path] for path in self.__modified_files
                }
                out = asyncio.run(
                    self.__compiler.compile(
                        {}, [SolcOutputSelectionEnum.AST], False, False, modified_files
                    )
                )
                self.__output = list(out)
                self.__output_contents = self.__files.copy()
                self.__modified_files.clear()

                if self.__file_changes_queue.empty():
                    self.output_ready.set()
