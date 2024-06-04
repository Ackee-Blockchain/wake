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

from wake.core import get_logger
from wake.ir.ast import AstNodeId, AstSolc
from wake.ir.enums import GlobalSymbol

if TYPE_CHECKING:
    from wake.ir.abc import SolidityAbc
    from wake.ir.expressions.identifier import Identifier
    from wake.ir.expressions.member_access import MemberAccess
    from wake.ir.meta.source_unit import SourceUnit


logger = get_logger(__name__)


@dataclass
class CallbackParams:
    interval_trees: Dict[Path, IntervalTree]
    source_units: Dict[Path, SourceUnit]


@dataclass(order=True)
class PostProcessQueueItem:
    priority: int
    callback: Callable[[CallbackParams], None] = field(compare=False)


class ReferenceResolver:
    """
    The reference resolver is responsible for resolving references between IR nodes.

    A single Solidity source file can be compiled in multiple compilation units (CUs).
    Each CU may use different AST node IDs for the same AST node.
    The reference resolver can map between different AST node IDs for the same AST node by indexing the AST IDs by their file path and traversal order.
    Different compiler versions may produce (structurally) different ASTs for the same source code. All of these cases should be handled by the reference resolver.

    Wake holds only a single [SourceUnit][wake.ir.meta.source_unit.SourceUnit] IR node for each source file.
    If a source file is compiled in multiple CUs, a canonical AST representation is chosen and the other CUs only perform indexing of the AST nodes.
    Which CU is chosen as the canonical is internal to Wake and should not be relied upon.

    A unique identifier across all CUs is a tuple (path, traversal_order).
    """

    _ordered_nodes: DefaultDict[bytes, Dict[AstNodeId, Tuple[Path, int]]]
    _ordered_nodes_inverted: DefaultDict[bytes, Dict[Tuple[Path, int], AstNodeId]]
    _registered_source_files: DefaultDict[bytes, Dict[int, Path]]
    _registered_nodes: Dict[Tuple[Path, int], SolidityAbc]
    _post_process_callbacks: List[PostProcessQueueItem]
    _destroy_callbacks: DefaultDict[Path, List[Callable[[], None]]]
    _global_symbol_references: DefaultDict[
        GlobalSymbol, List[Union[Identifier, MemberAccess]]
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

    def clear_all_indexed_nodes(self) -> None:
        self._node_types.clear()

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
                prev_other_type = self._node_types[path].get(index - 1)
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
                        prev_other_type == "UserDefinedTypeName"
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
        """
        Get the (path, traversal_order) for a given AST node ID in a given CU.

        Args:
            node_id: AST node ID
            cu_hash: hash of the compilation unit that contains the AST node ID

        Returns:
            Tuple of (path, traversal_order) for the AST node ID
        """
        return self._ordered_nodes[cu_hash][node_id]

    def get_ast_id_from_cu_node_path_order(
        self, node_path_order: Tuple[Path, int], cu_hash: bytes
    ) -> AstNodeId:
        """
        Get the AST node ID for a given (path, traversal_order) in a given CU.

        Args:
            node_path_order: (path, traversal_order) tuple
            cu_hash: hash of the compilation unit that contains the returned AST node ID

        Returns:
            AST node ID for the given (path, traversal_order) tuple in the given CU
        """
        return self._ordered_nodes_inverted[cu_hash][node_path_order]

    def register_node(self, node: SolidityAbc, node_id: AstNodeId, cu_hash: bytes):
        assert cu_hash in self._ordered_nodes
        assert node_id in self._ordered_nodes[cu_hash]
        node_path_order = self._ordered_nodes[cu_hash][node_id]
        self._registered_nodes[node_path_order] = node

    def resolve_node(self, node_id: AstNodeId, cu_hash: bytes) -> SolidityAbc:
        """
        Get the IR node for a given AST node ID in a given CU.

        Args:
            node_id: AST node ID
            cu_hash: hash of the compilation unit that contains the AST node ID

        Returns:
            IR node for the given AST node ID in the given CU
        """
        node_path_order = self._ordered_nodes[cu_hash][node_id]
        return self._registered_nodes[node_path_order]

    def resolve_source_file_id(self, source_file_id: int, cu_hash: bytes) -> Path:
        """
        `solc` compiler output also assigns integer IDs to source files.
        This function can be used to get the absolute path to the source file for a given source file ID in a given CU.

        Args:
            source_file_id: source file ID
            cu_hash: hash of the compilation unit that contains the source file ID

        Returns:
            Absolute path to the source file for the given source file ID in the given CU
        """
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
        self, node_id: GlobalSymbol, node: Union[Identifier, MemberAccess]
    ):
        self._global_symbol_references[node_id].append(node)

    def unregister_global_symbol_reference(
        self, node_id: GlobalSymbol, node: Union[Identifier, MemberAccess]
    ):
        self._global_symbol_references[node_id].remove(node)

    def get_global_symbol_references(
        self, node_id: GlobalSymbol
    ) -> Tuple[Union[Identifier, MemberAccess], ...]:
        """
        Get all references to a given global symbol.

        Args:
            node_id: global symbol

        Returns:
            Tuple of all references to the given global symbol
        """
        return tuple(self._global_symbol_references[node_id])
