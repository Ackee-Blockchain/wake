from __future__ import annotations

import re
from functools import lru_cache, partial
from pathlib import Path
from typing import TYPE_CHECKING, FrozenSet, Iterator, Optional, Set, Tuple, Union

from intervaltree import IntervalTree

from woke.ast.enums import (
    InlineAssemblyEvmVersion,
    InlineAssemblyFlag,
    InlineAssemblySuffix,
    ModifiesStateFlag,
)
from woke.ast.ir.abc import IrAbc, SolidityAbc
from woke.ast.ir.declaration.abc import DeclarationAbc
from woke.ast.ir.reference_resolver import CallbackParams, ReferenceResolver
from woke.ast.ir.statement.abc import StatementAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.ir.yul.block import Block as YulBlock
from woke.ast.nodes import AstNodeId, ExternalReferenceModel, SolcInlineAssembly

from ..yul.identifier import Identifier

if TYPE_CHECKING:
    from .block import Block
    from .do_while_statement import DoWhileStatement
    from .for_statement import ForStatement
    from .if_statement import IfStatement
    from .unchecked_block import UncheckedBlock
    from .while_statement import WhileStatement


IDENTIFIER_RE = re.compile(r"^[a-zA-Z$_][a-zA-Z0-9$_]*".encode("utf-8"))


class ExternalReference:
    """
    Reference from an inline assembly block to a Solidity declaration.
    !!! warning
        This is not an IR node, but a helper class for [InlineAssembly][woke.ast.ir.statement.inline_assembly.InlineAssembly].
        Since this is not an IR node, there must still be a Yul IR node (Yul [Identifier][woke.ast.ir.yul.identifier.Identifier]) in the source code that represents the identifier.
    """

    _inline_assembly: InlineAssembly
    _external_reference_model: ExternalReferenceModel
    _reference_resolver: ReferenceResolver
    _cu_hash: bytes
    _file: Path
    _source: bytes

    _referenced_declaration_id: AstNodeId
    _value_size: int
    _suffix: Optional[InlineAssemblySuffix]
    _yul_identifier: Optional[Identifier]

    def __init__(
        self,
        inline_assembly: InlineAssembly,
        init: IrInitTuple,
        external_reference_model: ExternalReferenceModel,
    ):
        self._inline_assembly = inline_assembly
        self._external_reference_model = external_reference_model
        self._reference_resolver = init.reference_resolver
        self._cu_hash = init.cu.hash
        self._file = init.file
        self._source = init.source[self.byte_location[0] : self.byte_location[1]]

        self._referenced_declaration_id = external_reference_model.declaration
        assert self._referenced_declaration_id >= 0
        self._value_size = external_reference_model.value_size
        self._suffix = external_reference_model.suffix
        self._yul_identifier = None

        if external_reference_model.is_offset:
            self._suffix = InlineAssemblySuffix.OFFSET
        elif external_reference_model.is_slot:
            self._suffix = InlineAssemblySuffix.SLOT

        self._reference_resolver.register_post_process_callback(self._post_process)

    def _post_process(self, callback_params: CallbackParams):
        referenced_declaration = self.referenced_declaration
        referenced_declaration.register_reference(self)
        self._reference_resolver.register_destroy_callback(
            self._file, partial(self._destroy, referenced_declaration)
        )
        interval_tree = callback_params.interval_trees[self._file]
        start, end = self.byte_location
        nodes = interval_tree[start:end]
        node = next(node for node in nodes if node.begin == start and node.end == end)
        assert isinstance(
            node.data, Identifier
        ), f"Expected Identifier, got {type(node.data)}"
        self._yul_identifier = node.data
        self._yul_identifier._external_reference = self

    def _destroy(self, referenced_declaration: DeclarationAbc) -> None:
        referenced_declaration.unregister_reference(self)

    @property
    def file(self) -> Path:
        """
        Returns:
            Absolute path to the file containing the inline assembly block.
        """
        return self._file

    @property
    def byte_location(self) -> Tuple[int, int]:
        """
        Returns:
            Byte offsets (start and end) of the external reference in the source file.
        """
        return (
            self._external_reference_model.src.byte_offset,
            self._external_reference_model.src.byte_offset
            + self._external_reference_model.src.byte_length,
        )

    @property
    @lru_cache(maxsize=2048)
    def identifier_byte_location(self) -> Tuple[int, int]:
        """
        !!! example
            Returns the byte location of `stateVar` in line 6, not `stateVar.slot`:
            ```solidity linenums="1"
            contract Foo {
                uint stateVar;

                function f() public pure {
                    assembly {
                        let x := stateVar.slot
                    }
                }
            }
            ```
        Returns:
            Byte offsets (start and end) of the identifier representing the external reference in the source file.
        """
        match = IDENTIFIER_RE.match(self._source)
        assert match
        start = self.byte_location[0] + match.start()
        end = self.byte_location[0] + match.end()
        return start, end

    @property
    def referenced_declaration(self) -> DeclarationAbc:
        """
        Returns:
            Solidity declaration referenced by this external reference.
        """
        node = self._reference_resolver.resolve_node(
            self._referenced_declaration_id, self._cu_hash
        )
        assert isinstance(node, DeclarationAbc)
        return node

    @property
    def inline_assembly(self) -> InlineAssembly:
        """
        Returns:
            Inline assembly block this external references belongs to.
        """
        return self._inline_assembly

    @property
    def yul_identifier(self) -> Identifier:
        """
        Returns:
            Yul Identifier node representing this external reference.
        """
        assert isinstance(self._yul_identifier, Identifier)
        return self._yul_identifier

    @property
    def value_size(self) -> int:
        # TODO document this?
        return self._value_size

    @property
    def suffix(self) -> Optional[InlineAssemblySuffix]:
        """
        Returns:
            Suffix of the external reference, if any.
        """
        return self._suffix


class InlineAssembly(StatementAbc):
    """
    Inline assembly block in Solidity.
    !!! example
        ```solidity
        function f() public pure {
            assembly {
                let x := 1
                let y := 2
                let z := add(x, y)
            }
        }
        ```
    """

    _ast_node: SolcInlineAssembly
    _parent: Union[
        Block,
        DoWhileStatement,
        ForStatement,
        IfStatement,
        UncheckedBlock,
        WhileStatement,
    ]

    _yul_block: YulBlock
    _evm_version: InlineAssemblyEvmVersion
    _external_references: IntervalTree
    _flags: Set[InlineAssemblyFlag]

    def __init__(
        self,
        init: IrInitTuple,
        inline_assembly: SolcInlineAssembly,
        parent: SolidityAbc,
    ):
        super().__init__(init, inline_assembly, parent)
        self._yul_block = YulBlock(init, inline_assembly.ast, self)
        self._evm_version = inline_assembly.evm_version
        self._external_references = IntervalTree()
        self._flags = set()
        if inline_assembly.flags is not None:
            for flag in inline_assembly.flags:
                self._flags.add(InlineAssemblyFlag(flag))
        for external_reference in inline_assembly.external_references:
            start = external_reference.src.byte_offset
            end = start + external_reference.src.byte_length
            self._external_references[start:end] = ExternalReference(
                self, init, external_reference
            )

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        yield from self._yul_block

    @property
    def parent(
        self,
    ) -> Union[
        Block,
        DoWhileStatement,
        ForStatement,
        IfStatement,
        UncheckedBlock,
        WhileStatement,
    ]:
        """
        Returns:
            Parent IR node.
        """
        return self._parent

    @property
    def yul_block(self) -> YulBlock:
        """
        Returns:
            Yul block containing Yul IR nodes ([YulAbc][woke.ast.ir.yul.abc.YulAbc]).
        """
        return self._yul_block

    @property
    def evm_version(self) -> InlineAssemblyEvmVersion:
        """
        Depends on the version of the `solc` compiler used to compile the contract.
        Returns:
            EVM version used for the inline assembly block.
        """
        return self._evm_version

    @property
    def flags(self) -> FrozenSet[InlineAssemblyFlag]:
        """
        !!! example
            ```solidity
            function f() public pure {
                assembly ("memory-safe") {
                    let x := 1
                    let y := 2
                    let z := add(x, y)
                }
            }
            ```
        Returns:
            Flags decorating the inline assembly block.
        """
        return frozenset(self._flags)

    @property
    def external_references(self) -> Tuple[ExternalReference]:
        """
        Returns:
            External references in the inline assembly block.
        """
        return tuple(interval.data for interval in self._external_references)

    def external_reference_at(self, byte_offset: int) -> Optional[ExternalReference]:
        """
        Args:
            byte_offset: Byte offset in the source file.
        Returns:
            External reference at the given byte offset, if any.
        """
        intervals = self._external_references.at(byte_offset)
        assert len(intervals) <= 1
        if len(intervals) == 0:
            return None
        return intervals.pop().data

    @property
    @lru_cache(maxsize=2048)
    def modifies_state(self) -> Set[Tuple[IrAbc, ModifiesStateFlag]]:
        return self.yul_block.modifies_state
