from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Iterator, Optional, Tuple

from wake.ir.ast import SolcNode, SolidityNode
from wake.ir.reference_resolver import ReferenceResolver
from wake.ir.utils import IrInitTuple

if TYPE_CHECKING:
    from wake.ir.meta.source_unit import SourceUnit


class IrAbc(ABC):
    """
    Base class for all IR nodes. Defines attributes and methods that are common to all Solidity and Yul IR nodes.

    IR model is built on top of the AST (Abstract Syntax Tree) output of the [solc compiler](https://docs.soliditylang.org/en/latest/using-the-compiler.html).

    Each IR node is associated with a [source code location][wake.ir.abc.IrAbc.byte_location] in a [source file][wake.ir.meta.source_unit.SourceUnit.file].
    This means that each IR node has a corresponding (typically non-empty) Solidity or Yul [source code][wake.ir.abc.IrAbc.source].

    !!! info
        Yul IR nodes can have empty source code. In the case of Solidity IR nodes, this should not happen.

    """

    _source: bytes
    _ast_node: SolcNode
    _parent: Optional[IrAbc]
    _depth: int
    _source_unit: SourceUnit
    _reference_resolver: ReferenceResolver

    def __init__(self, init: IrInitTuple, solc_node: SolcNode, parent: Optional[IrAbc]):
        self._ast_node = solc_node
        self._parent = parent
        if self._parent is not None:
            self._depth = self._parent.ast_tree_depth + 1
        else:
            self._depth = 0

        assert init.source_unit is not None
        self._source_unit = init.source_unit
        self._reference_resolver = init.reference_resolver

        source_start = solc_node.src.byte_offset
        source_end = source_start + solc_node.src.byte_length
        self._source = init.source[source_start:source_end]
        if source_start != source_end:
            init.interval_tree[source_start:source_end] = self

    def __iter__(self) -> Iterator[IrAbc]:
        """
        Yields:
            Self and (recursively) all child IR nodes.
        """
        yield self

    @property
    @abstractmethod
    def parent(self) -> Optional[IrAbc]:
        """
        The parent node of this node. Can only be `None` for the root ([Source unit][wake.ir.meta.source_unit.SourceUnit]) node.

        Returns:
            Parent node of this node.
        """
        ...

    @property
    @abstractmethod
    def ast_node(self) -> SolcNode:
        ...

    @property
    def ast_tree_depth(self) -> int:
        """
        The depth of this node in the AST tree. The root node ([Source unit][wake.ir.meta.source_unit.SourceUnit]) of each file has depth 0. Direct child nodes of a `node` have depth `{node}.ast_tree_depth + 1`.

        !!! tip
            Wake uses [interval trees](https://github.com/chaimleib/intervaltree) to get a list of all IR nodes at a given byte offset in a given file. This property can be used to sort these nodes by their depth in the AST tree and (for example) to choose the most nested one.

        Returns:
            Depth of this node in the AST tree, starting from 0.

        """
        return self._depth

    @property
    def byte_location(self) -> Tuple[int, int]:
        """
        The byte location of a child node is typically a subrange of the byte location of its parent node.

        !!! info
            This is not true for [Structured documentation][wake.ir.meta.structured_documentation.StructuredDocumentation], where documentation strings must be located before a declaration.

        Returns:
            Tuple of the start and end byte offsets of this node in the source file.
        """
        return (
            self._ast_node.src.byte_offset,
            self._ast_node.src.byte_offset + self._ast_node.src.byte_length,
        )

    @property
    def source(self) -> str:
        """
        UTF-8 decoded source code from the [source file][wake.ir.meta.source_unit.SourceUnit.file] at the [byte offset][wake.ir.abc.IrAbc.byte_location] of this node.

        Returns:
            Solidity or Yul source code corresponding to this node.
        """
        return self._source.decode("utf-8")

    @property
    def source_unit(self) -> SourceUnit:
        """
        Returns:
            Source unit that contains this node.
        """
        return self._source_unit


class SolidityAbc(IrAbc, ABC):
    """
    Abstract base class for all Solidity IR nodes.
    """

    _ast_node: SolidityNode

    def __init__(
        self, init: IrInitTuple, solc_node: SolidityNode, parent: Optional[SolidityAbc]
    ):
        super().__init__(init, solc_node, parent)
        self._reference_resolver.register_node(
            self, solc_node.id, self.source_unit.cu_hash
        )

    @property
    def ast_node(self) -> SolidityNode:
        return self._ast_node

    @property
    def ast_node_id(self) -> int:
        return self._ast_node.id
