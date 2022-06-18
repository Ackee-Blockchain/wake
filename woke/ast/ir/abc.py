from abc import ABC

from woke.ast.nodes import SolcNode
from woke.compile.compilation_unit import CompilationUnit


class IrAbc(ABC):
    _source: bytes
    _ast_node: SolcNode

    def __init__(self, solc_node: SolcNode, source: bytes, cu: CompilationUnit):
        self._ast_node = solc_node
        self._source = source[
            solc_node.src.byte_offset : solc_node.src.byte_offset
            + solc_node.src.byte_length
        ]
