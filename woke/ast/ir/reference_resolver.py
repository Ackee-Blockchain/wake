from __future__ import annotations

from typing import TYPE_CHECKING, Dict

if TYPE_CHECKING:
    from woke.ast.ir.abc import IrAbc

from woke.ast.nodes import AstNodeId


class ReferenceResolver:
    __registered_nodes: Dict[bytes, Dict[AstNodeId, IrAbc]]

    def __init__(self):
        self.__registered_nodes = {}

    def register_node(self, node: IrAbc, node_id: AstNodeId, cu_hash: bytes):
        if cu_hash not in self.__registered_nodes:
            self.__registered_nodes[cu_hash] = {}
        self.__registered_nodes[cu_hash][node_id] = node

    def resolve_node(self, node_id: AstNodeId, cu_hash: bytes) -> IrAbc:
        return self.__registered_nodes[cu_hash][node_id]
