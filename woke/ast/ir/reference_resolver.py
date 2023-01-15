from __future__ import annotations

import heapq
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Callable, DefaultDict, Dict, List, Tuple, Union

from intervaltree import IntervalTree

from woke.ast.enums import GlobalSymbolsEnum

if TYPE_CHECKING:
    from woke.ast.ir.abc import SolidityAbc
    from woke.ast.ir.expression.identifier import Identifier
    from woke.ast.ir.expression.member_access import MemberAccess
    from woke.ast.ir.meta.source_unit import SourceUnit

from woke.ast.nodes import AstNodeId, AstSolc

logger = logging.getLogger(__name__)


@dataclass
class CallbackParams:
    interval_trees: Dict[Path, IntervalTree]
    source_units: Dict[Path, SourceUnit]


@dataclass(order=True)
class PostProcessQueueItem:
    priority: int
    callback: Callable[[CallbackParams], None] = field(compare=False)


class ReferenceResolver:
    __ordered_nodes: DefaultDict[bytes, Dict[AstNodeId, Tuple[Path, int]]]
    __ordered_nodes_inverted: DefaultDict[bytes, Dict[Tuple[Path, int], AstNodeId]]
    __registered_source_files: DefaultDict[bytes, Dict[int, Path]]
    __registered_nodes: Dict[Tuple[Path, int], SolidityAbc]
    __post_process_callbacks: List[PostProcessQueueItem]
    __destroy_callbacks: DefaultDict[Path, List[Callable[[], None]]]
    __global_symbol_references: DefaultDict[
        GlobalSymbolsEnum, List[Union[Identifier, MemberAccess]]
    ]

    def __init__(self):
        self.__ordered_nodes = defaultdict(dict)
        self.__ordered_nodes_inverted = defaultdict(dict)
        self.__registered_source_files = defaultdict(dict)
        self.__registered_nodes = {}
        self.__post_process_callbacks = []
        self.__destroy_callbacks = defaultdict(list)
        self.__global_symbol_references = defaultdict(list)

    def index_nodes(self, root_node: AstSolc, path: Path, cu_hash: bytes) -> None:
        self.__ordered_nodes[cu_hash][root_node.id] = (path, 0)
        self.__ordered_nodes_inverted[cu_hash][(path, 0)] = root_node.id
        for index, node in enumerate(root_node):
            self.__ordered_nodes[cu_hash][node.id] = (path, index + 1)
            self.__ordered_nodes_inverted[cu_hash][(path, index + 1)] = node.id

    def register_source_file_id(self, source_file_id: int, path: Path, cu_hash: bytes):
        self.__registered_source_files[cu_hash][source_file_id] = path

    def get_node_path_order(
        self, node_id: AstNodeId, cu_hash: bytes
    ) -> Tuple[Path, int]:
        return self.__ordered_nodes[cu_hash][node_id]

    def get_ast_id_from_cu_node_path_order(
        self, node_path_order: Tuple[Path, int], cu_hash: bytes
    ) -> AstNodeId:
        return self.__ordered_nodes_inverted[cu_hash][node_path_order]

    def register_node(self, node: SolidityAbc, node_id: AstNodeId, cu_hash: bytes):
        assert cu_hash in self.__ordered_nodes
        assert node_id in self.__ordered_nodes[cu_hash]
        node_path_order = self.__ordered_nodes[cu_hash][node_id]
        self.__registered_nodes[node_path_order] = node

    def resolve_node(self, node_id: AstNodeId, cu_hash: bytes) -> SolidityAbc:
        node_path_order = self.__ordered_nodes[cu_hash][node_id]
        return self.__registered_nodes[node_path_order]

    def resolve_source_file_id(self, source_file_id: int, cu_hash: bytes) -> Path:
        return self.__registered_source_files[cu_hash][source_file_id]

    def register_post_process_callback(
        self, callback: Callable[[CallbackParams], None], priority: int = 0
    ):
        heapq.heappush(
            self.__post_process_callbacks, PostProcessQueueItem(priority, callback)
        )

    def register_destroy_callback(self, file: Path, callback: Callable[[], None]):
        self.__destroy_callbacks[file].append(callback)

    def run_post_process_callbacks(self, callback_params: CallbackParams):
        while len(self.__post_process_callbacks):
            callback = heapq.heappop(self.__post_process_callbacks).callback
            callback(callback_params)

    def run_destroy_callbacks(self, file: Path):
        for callback in self.__destroy_callbacks[file]:
            callback()
        del self.__destroy_callbacks[file]

    def register_global_symbol_reference(
        self, node_id: GlobalSymbolsEnum, node: Union[Identifier, MemberAccess]
    ):
        self.__global_symbol_references[node_id].append(node)

    def unregister_global_symbol_reference(
        self, node_id: GlobalSymbolsEnum, node: Union[Identifier, MemberAccess]
    ):
        self.__global_symbol_references[node_id].remove(node)

    def get_global_symbol_references(
        self, node_id: GlobalSymbolsEnum
    ) -> Tuple[Union[Identifier, MemberAccess], ...]:
        return tuple(self.__global_symbol_references[node_id])
