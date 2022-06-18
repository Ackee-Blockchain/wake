from abc import ABC
from pathlib import Path
from typing import Optional

from woke.ast.ir.utils.init_tuple import IrInitTuple
from woke.ast.nodes import SolcNode


class IrAbc(ABC):
    _file: Path
    _source: bytes
    _ast_node: SolcNode
    _parent: Optional["IrAbc"]
    _depth: int

    def __init__(
        self, init: IrInitTuple, solc_node: SolcNode, parent: Optional["IrAbc"]
    ):
        self._file = init.file
        self._ast_node = solc_node
        self._parent = parent
        if self._parent is not None:
            self._depth = self._parent.ast_tree_depth + 1
        else:
            self._depth = 0
        self._source = init.source[
            solc_node.src.byte_offset : solc_node.src.byte_offset
            + solc_node.src.byte_length
        ]

    @property
    def file(self) -> Path:
        return self._file

    @property
    def ast_tree_depth(self) -> int:
        return self._depth
