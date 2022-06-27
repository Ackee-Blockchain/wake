from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from queue import PriorityQueue
from typing import TYPE_CHECKING, Callable, Dict, List, Tuple

from woke.ast.enums import GlobalSymbolsEnum

if TYPE_CHECKING:
    from woke.ast.ir.abc import IrAbc
    from woke.ast.ir.expression.identifier import Identifier
    from woke.ast.ir.meta.source_unit import SourceUnit

from woke.ast.nodes import AstNodeId


@dataclass
class CallbackParams:
    source_units: Dict[Path, SourceUnit]


@dataclass(order=True)
class PostProcessQueueItem:
    priority: int
    callback: Callable[[CallbackParams], None] = field(compare=False)


class ReferenceResolver:
    __registered_nodes: Dict[bytes, Dict[AstNodeId, IrAbc]]
    __post_process_callbacks: PriorityQueue[PostProcessQueueItem]
    __global_symbol_references: Dict[GlobalSymbolsEnum, List[Identifier]]

    def __init__(self):
        self.__registered_nodes = {}
        self.__post_process_callbacks = PriorityQueue()
        self.__global_symbol_references = {}

    def register_node(self, node: IrAbc, node_id: AstNodeId, cu_hash: bytes):
        if cu_hash not in self.__registered_nodes:
            self.__registered_nodes[cu_hash] = {}
        self.__registered_nodes[cu_hash][node_id] = node

    def resolve_node(self, node_id: AstNodeId, cu_hash: bytes) -> IrAbc:
        return self.__registered_nodes[cu_hash][node_id]

    def register_post_process_callback(
        self, callback: Callable[[CallbackParams], None], priority: int = 0
    ):
        self.__post_process_callbacks.put(PostProcessQueueItem(priority, callback))

    def run_post_process_callbacks(self, callback_params: CallbackParams):
        while not self.__post_process_callbacks.empty():
            callback = self.__post_process_callbacks.get().callback
            callback(callback_params)

    def register_global_symbol_reference(
        self, node_id: GlobalSymbolsEnum, node: Identifier
    ):
        if node_id not in self.__global_symbol_references:
            self.__global_symbol_references[node_id] = []
        self.__global_symbol_references[node_id].append(node)

    def get_global_symbol_references(
        self, node_id: GlobalSymbolsEnum
    ) -> Tuple[Identifier, ...]:
        return tuple(self.__global_symbol_references[node_id])
