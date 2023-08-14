from __future__ import annotations

from abc import ABCMeta, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, List

from woke.core.visitor import Visitor, visit_map

if TYPE_CHECKING:
    from rich.console import Console


class Printer(Visitor, metaclass=ABCMeta):
    console: Console
    paths: List[Path]

    @abstractmethod
    def print(self) -> None:
        ...

    def _run(self) -> None:
        from woke.utils.file_utils import is_relative_to

        for path, source_unit in self.build.source_units.items():
            if len(self.paths) == 0 or any(is_relative_to(path, p) for p in self.paths):
                for node in source_unit:
                    visit_map[node.ast_node.node_type](self, node)

        self.print()
