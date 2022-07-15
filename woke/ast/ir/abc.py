from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Tuple

from woke.ast.ir.reference_resolver import ReferenceResolver
from woke.ast.ir.utils.init_tuple import IrInitTuple
from woke.ast.nodes import SolcNode


class IrAbc(ABC):
    _file: Path
    _source: bytes
    _ast_node: SolcNode
    _parent: Optional["IrAbc"]
    _depth: int
    _cu_hash: bytes
    _reference_resolver: ReferenceResolver

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
        self._cu_hash = init.cu.hash

        self._reference_resolver = init.reference_resolver
        self._reference_resolver.register_node(self, solc_node.id, self._cu_hash)

        source_start = solc_node.src.byte_offset
        source_end = source_start + solc_node.src.byte_length
        self._source = init.source[source_start:source_end]
        if source_start != source_end:
            init.interval_tree[source_start:source_end] = self

    @property
    @abstractmethod
    def parent(self) -> Optional["IrAbc"]:
        ...

    @property
    def file(self) -> Path:
        return self._file

    @property
    def ast_node_id(self) -> int:
        return self._ast_node.id

    @property
    def cu_hash(self) -> bytes:
        return self._cu_hash

    @property
    def ast_tree_depth(self) -> int:
        return self._depth

    @property
    def byte_location(self) -> Tuple[int, int]:
        return (
            self._ast_node.src.byte_offset,
            self._ast_node.src.byte_offset + self._ast_node.src.byte_length,
        )
