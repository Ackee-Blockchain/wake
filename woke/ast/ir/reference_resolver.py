from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from queue import PriorityQueue
from typing import TYPE_CHECKING, Callable, DefaultDict, Dict, List, Tuple

from woke.ast.enums import GlobalSymbolsEnum

if TYPE_CHECKING:
    from woke.ast.ir.abc import IrAbc
    from woke.ast.ir.expression.identifier import Identifier
    from woke.ast.ir.meta.source_unit import SourceUnit

from woke.ast.nodes import AstNodeId, AstSolc

logger = logging.getLogger(__name__)


@dataclass
class CallbackParams:
    source_units: Dict[Path, SourceUnit]


@dataclass(order=True)
class PostProcessQueueItem:
    priority: int
    callback: Callable[[CallbackParams], None] = field(compare=False)


class ReferenceResolver:
    __ordered_nodes: Dict[bytes, Dict[AstNodeId, Tuple[Path, int]]]
    __registered_nodes: Dict[Tuple[Path, int], IrAbc]
    __post_process_callbacks: PriorityQueue[PostProcessQueueItem]
    __destroy_callbacks: DefaultDict[Path, List[Callable[[], None]]]
    __global_symbol_references: Dict[GlobalSymbolsEnum, List[Identifier]]

    def __init__(self):
        self.__ordered_nodes = defaultdict(dict)
        self.__registered_nodes = {}
        self.__post_process_callbacks = PriorityQueue()
        self.__destroy_callbacks = defaultdict(list)
        self.__global_symbol_references = {}

    def index_nodes(self, root_node: AstSolc, path: Path, cu_hash: bytes) -> None:
        self.__ordered_nodes[cu_hash][root_node.id] = (path, 0)
        for index, node in enumerate(root_node):
            self.__ordered_nodes[cu_hash][node.id] = (path, index + 1)

    def get_node_path_order(
        self, node_id: AstNodeId, cu_hash: bytes
    ) -> Tuple[Path, int]:
        return self.__ordered_nodes[cu_hash][node_id]

    def get_ast_id_from_cu_node_path_order(
        self, node_path_order: Tuple[Path, int], cu_hash: bytes
    ) -> AstNodeId:
        for node_id, node_path_order_ in self.__ordered_nodes[cu_hash].items():
            if node_path_order_ == node_path_order:
                return node_id
        raise KeyError(
            f"No node found for path order {node_path_order} cu hash {cu_hash.hex()}"
        )

    def register_node(self, node: IrAbc, node_id: AstNodeId, cu_hash: bytes):
        assert cu_hash in self.__ordered_nodes
        assert node_id in self.__ordered_nodes[cu_hash]
        node_path_order = self.__ordered_nodes[cu_hash][node_id]
        self.__registered_nodes[node_path_order] = node

    def resolve_node(self, node_id: AstNodeId, cu_hash: bytes) -> IrAbc:
        node_path_order = self.__ordered_nodes[cu_hash][node_id]
        return self.__registered_nodes[node_path_order]

    def register_post_process_callback(
        self, callback: Callable[[CallbackParams], None], priority: int = 0
    ):
        self.__post_process_callbacks.put(PostProcessQueueItem(priority, callback))

    def register_destroy_callback(self, file: Path, callback: Callable[[], None]):
        self.__destroy_callbacks[file].append(callback)

    def run_post_process_callbacks(self, callback_params: CallbackParams):
        while not self.__post_process_callbacks.empty():
            callback = self.__post_process_callbacks.get().callback
            callback(callback_params)

    def run_destroy_callbacks(self, file: Path):
        for callback in self.__destroy_callbacks[file]:
            callback()
        del self.__destroy_callbacks[file]

    def register_global_symbol_reference(
        self, node_id: GlobalSymbolsEnum, node: Identifier
    ):
        if node_id not in self.__global_symbol_references:
            self.__global_symbol_references[node_id] = []
        self.__global_symbol_references[node_id].append(node)

    def unregister_global_symbol_reference(
        self, node_id: GlobalSymbolsEnum, node: Identifier
    ):
        self.__global_symbol_references[node_id].remove(node)
        if not self.__global_symbol_references[node_id]:
            del self.__global_symbol_references[node_id]

    def get_global_symbol_references(
        self, node_id: GlobalSymbolsEnum
    ) -> Tuple[Identifier, ...]:
        return tuple(self.__global_symbol_references[node_id])
