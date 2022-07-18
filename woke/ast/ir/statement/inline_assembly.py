import re
from functools import lru_cache, partial
from pathlib import Path
from typing import List, Optional, Tuple

from intervaltree import IntervalTree

from woke.ast.enums import InlineAssemblyEvmVersion, InlineAssemblySuffix
from woke.ast.ir.abc import IrAbc
from woke.ast.ir.declaration.abc import DeclarationAbc
from woke.ast.ir.reference_resolver import CallbackParams, ReferenceResolver
from woke.ast.ir.statement.abc import StatementAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import AstNodeId, ExternalReferenceModel, SolcInlineAssembly

IDENTIFIER_RE = re.compile(r"^[a-zA-Z$_][a-zA-Z0-9$_]*".encode("utf-8"))


class ExternalReference:
    __external_reference_model: ExternalReferenceModel
    __reference_resolver: ReferenceResolver
    __cu_hash: bytes
    __file: Path
    __source: bytes

    __referenced_declaration_id: AstNodeId
    __is_offset: bool
    __is_slot: bool
    __value_size: int
    __suffix: Optional[InlineAssemblySuffix]

    def __init__(
        self, init: IrInitTuple, external_reference_model: ExternalReferenceModel
    ):
        self.__external_reference_model = external_reference_model
        self.__reference_resolver = init.reference_resolver
        self.__cu_hash = init.cu.hash
        self.__file = init.file
        self.__source = init.source[self.byte_location[0] : self.byte_location[1]]

        self.__referenced_declaration_id = external_reference_model.declaration
        assert self.__referenced_declaration_id >= 0
        self.__is_offset = external_reference_model.is_offset
        self.__is_slot = external_reference_model.is_slot
        self.__value_size = external_reference_model.value_size
        self.__suffix = external_reference_model.suffix

        self.__reference_resolver.register_post_process_callback(self.__post_process)

    def __post_process(self, callback_params: CallbackParams):
        referenced_declaration = self.referenced_declaration
        referenced_declaration.register_reference(self)
        self.__reference_resolver.register_destroy_callback(
            self.__file, partial(self.__destroy, referenced_declaration)
        )

    def __destroy(self, referenced_declaration: DeclarationAbc) -> None:
        referenced_declaration.unregister_reference(self)

    @property
    def file(self) -> Path:
        return self.__file

    @property
    def byte_location(self) -> Tuple[int, int]:
        return (
            self.__external_reference_model.src.byte_offset,
            self.__external_reference_model.src.byte_offset
            + self.__external_reference_model.src.byte_length,
        )

    @property
    @lru_cache(maxsize=None)
    def identifier_byte_location(self) -> Tuple[int, int]:
        match = IDENTIFIER_RE.match(self.__source)
        assert match
        start = self.byte_location[0] + match.start()
        end = self.byte_location[0] + match.end()
        return start, end

    @property
    def referenced_declaration(self) -> DeclarationAbc:
        node = self.__reference_resolver.resolve_node(
            self.__referenced_declaration_id, self.__cu_hash
        )
        assert isinstance(node, DeclarationAbc)
        return node

    @property
    def is_offset(self) -> bool:
        return self.__is_offset

    @property
    def is_slot(self) -> bool:
        return self.__is_slot

    @property
    def value_size(self) -> int:
        return self.__value_size

    @property
    def suffix(self) -> Optional[InlineAssemblySuffix]:
        return self.__suffix


class InlineAssembly(StatementAbc):
    _ast_node: SolcInlineAssembly
    _parent: IrAbc  # TODO: make this more specific

    # __ast: TODO
    __evm_version: InlineAssemblyEvmVersion
    __external_references: IntervalTree
    __documentation: Optional[str]

    def __init__(
        self, init: IrInitTuple, inline_assembly: SolcInlineAssembly, parent: IrAbc
    ):
        super().__init__(init, inline_assembly, parent)
        self.__evm_version = inline_assembly.evm_version
        self.__documentation = inline_assembly.documentation
        self.__external_references = IntervalTree()
        for external_reference in inline_assembly.external_references:
            start = external_reference.src.byte_offset
            end = start + external_reference.src.byte_length
            self.__external_references[start:end] = ExternalReference(
                init, external_reference
            )

    @property
    def parent(self) -> IrAbc:
        return self._parent

    @property
    def evm_version(self) -> InlineAssemblyEvmVersion:
        return self.__evm_version

    @property
    def documentation(self) -> Optional[str]:
        return self.__documentation

    @property
    def external_references(self) -> Tuple[ExternalReference]:
        return tuple(interval.data for interval in self.__external_references)

    def external_reference_at(self, byte_offset: int) -> Optional[ExternalReference]:
        intervals = self.__external_references.at(byte_offset)
        assert len(intervals) <= 1
        if len(intervals) == 0:
            return None
        return intervals.pop().data
