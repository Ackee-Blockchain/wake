from __future__ import annotations

import heapq
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Callable,
    DefaultDict,
    Dict,
    Iterable,
    List,
    Tuple,
    Union,
)

from intervaltree import IntervalTree

from woke.ir.enums import GlobalSymbolsEnum

if TYPE_CHECKING:
    from woke.ir.abc import SolidityAbc
    from woke.ir.expressions.identifier import Identifier
    from woke.ir.expressions.member_access import MemberAccess
    from woke.ir.meta.source_unit import SourceUnit

from woke.ir.ast import AstNodeId, AstSolc

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
    _ordered_nodes: DefaultDict[bytes, Dict[AstNodeId, Tuple[Path, int]]]
    _ordered_nodes_inverted: DefaultDict[bytes, Dict[Tuple[Path, int], AstNodeId]]
    _registered_source_files: DefaultDict[bytes, Dict[int, Path]]
    _registered_nodes: Dict[Tuple[Path, int], SolidityAbc]
    _post_process_callbacks: List[PostProcessQueueItem]
    _destroy_callbacks: DefaultDict[Path, List[Callable[[], None]]]
    _global_symbol_references: DefaultDict[
        GlobalSymbolsEnum, List[Union[Identifier, MemberAccess]]
    ]
    _node_types: Dict[Path, Dict[int, str]]

    def __init__(self):
        self._ordered_nodes = defaultdict(dict)
        self._ordered_nodes_inverted = defaultdict(dict)
        self._registered_source_files = defaultdict(dict)
        self._registered_nodes = {}
        self._post_process_callbacks = []
        self._destroy_callbacks = defaultdict(list)
        self._global_symbol_references = defaultdict(list)
        self._node_types = {}

    def clear_indexed_nodes(self, paths: Iterable[Path]) -> None:
        for path in paths:
            self._node_types.pop(path, None)

    def index_nodes(self, root_node: AstSolc, path: Path, cu_hash: bytes) -> None:
        if path not in self._node_types:
            self._node_types[path] = {}
            self._node_types[path][0] = root_node.node_type
            check = False
        else:
            assert self._node_types[path][0] == root_node.node_type
            check = True
        prev_type = root_node.node_type

        self._ordered_nodes[cu_hash][root_node.id] = (path, 0)
        self._ordered_nodes_inverted[cu_hash][(path, 0)] = root_node.id
        index = 1
        for node in root_node:
            if check:
                skip = False
                other_type = self._node_types[path].get(index)

                while other_type != node.node_type:
                    if other_type == "StructuredDocumentation":
                        index += 1
                        other_type = self._node_types[path].get(index)
                        continue
                    elif node.node_type == "StructuredDocumentation":
                        skip = True
                        prev_type = "StructuredDocumentation"
                        break
                    elif (
                        self._node_types[path][index - 1] == "UserDefinedTypeName"
                        and prev_type == "UserDefinedTypeName"
                    ):
                        if other_type == "IdentifierPath":
                            index += 1
                            other_type = self._node_types[path].get(index)
                            continue
                        elif node.node_type == "IdentifierPath":
                            skip = True
                            prev_type = "IdentifierPath"
                            break
                    elif (
                        other_type == "IdentifierPath"
                        and node.node_type == "UserDefinedTypeName"
                    ) or (
                        other_type == "UserDefinedTypeName"
                        and node.node_type == "IdentifierPath"
                    ):
                        break

                    assert (
                        other_type == node.node_type
                    ), f"Expected {other_type} but got {node.node_type} at {path}:{index} {node.id}"

                if skip:
                    continue
            else:
                self._node_types[path][index] = node.node_type

            self._ordered_nodes[cu_hash][node.id] = (path, index)
            self._ordered_nodes_inverted[cu_hash][(path, index)] = node.id

            prev_type = node.node_type
            index += 1

    def register_source_file_id(self, source_file_id: int, path: Path, cu_hash: bytes):
        self._registered_source_files[cu_hash][source_file_id] = path

    def get_node_path_order(
        self, node_id: AstNodeId, cu_hash: bytes
    ) -> Tuple[Path, int]:
        return self._ordered_nodes[cu_hash][node_id]

    def get_ast_id_from_cu_node_path_order(
        self, node_path_order: Tuple[Path, int], cu_hash: bytes
    ) -> AstNodeId:
        return self._ordered_nodes_inverted[cu_hash][node_path_order]

    def register_node(self, node: SolidityAbc, node_id: AstNodeId, cu_hash: bytes):
        assert cu_hash in self._ordered_nodes
        assert node_id in self._ordered_nodes[cu_hash]
        node_path_order = self._ordered_nodes[cu_hash][node_id]
        self._registered_nodes[node_path_order] = node

    def resolve_node(self, node_id: AstNodeId, cu_hash: bytes) -> SolidityAbc:
        node_path_order = self._ordered_nodes[cu_hash][node_id]
        return self._registered_nodes[node_path_order]

    def resolve_source_file_id(self, source_file_id: int, cu_hash: bytes) -> Path:
        return self._registered_source_files[cu_hash][source_file_id]

    def register_post_process_callback(
        self, callback: Callable[[CallbackParams], None], priority: int = 0
    ):
        heapq.heappush(
            self._post_process_callbacks, PostProcessQueueItem(priority, callback)
        )

    def register_destroy_callback(self, file: Path, callback: Callable[[], None]):
        self._destroy_callbacks[file].append(callback)

    def run_post_process_callbacks(self, callback_params: CallbackParams):
        while len(self._post_process_callbacks):
            callback = heapq.heappop(self._post_process_callbacks).callback
            callback(callback_params)

    def run_destroy_callbacks(self, file: Path):
        for callback in self._destroy_callbacks[file]:
            callback()
        del self._destroy_callbacks[file]

    def register_global_symbol_reference(
        self, node_id: GlobalSymbolsEnum, node: Union[Identifier, MemberAccess]
    ):
        self._global_symbol_references[node_id].append(node)

    def unregister_global_symbol_reference(
        self, node_id: GlobalSymbolsEnum, node: Union[Identifier, MemberAccess]
    ):
        self._global_symbol_references[node_id].remove(node)

    def get_global_symbol_references(
        self, node_id: GlobalSymbolsEnum
    ) -> Tuple[Union[Identifier, MemberAccess], ...]:
        return tuple(self._global_symbol_references[node_id])
