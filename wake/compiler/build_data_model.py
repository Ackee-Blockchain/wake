import weakref
from pathlib import Path, PurePath
from types import MappingProxyType
from typing import Any, Dict, FrozenSet, List, Optional

from intervaltree import IntervalTree
from pydantic import (
    BaseModel,
    ConfigDict,
    PlainSerializer,
    PlainValidator,
    WithJsonSchema,
    errors,
    field_serializer,
    field_validator,
)
from typing_extensions import Annotated

from wake.compiler.solc_frontend import SolcInputSettings, SolcOutputError
from wake.core.solidity_version import SolidityVersion
from wake.ir import (
    BinaryOperation,
    ContractDefinition,
    DeclarationAbc,
    EventDefinition,
    FunctionDefinition,
    Identifier,
    IdentifierPath,
    InlineAssembly,
    MemberAccess,
    ModifierDefinition,
    SolidityAbc,
    SourceUnit,
    UnaryOperation,
    UserDefinedTypeName,
    VariableDeclaration,
    YulAbc,
    YulIdentifier,
)
from wake.ir.enums import GlobalSymbol
from wake.ir.reference_resolver import ReferenceResolver


def hex_bytes_validator(val: Any) -> bytes:
    if isinstance(val, bytes):
        return val
    elif isinstance(val, bytearray):
        return bytes(val)
    elif isinstance(val, str):
        return bytes.fromhex(val)
    raise errors.BytesError()


HexBytes = Annotated[
    bytes,
    PlainValidator(hex_bytes_validator),
    PlainSerializer(lambda b: b.hex()),
    WithJsonSchema({"type": "string"}),
]


class BuildInfoModel(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        frozen=True,
    )


class CompilationUnitBuildInfo(BuildInfoModel):
    """
    Holds all compilation errors and warnings that occurred during compilation of a single compilation unit.
    Some errors and warnings may not be associated with any specific source code location.
    Because of incremental compilation, it is important to keep track of all errors and warnings that occurred during compilation of a compilation unit with a given hash.

    Attributes:
        errors: List of compilation warnings and errors that occurred during compilation of the compilation unit.
    """

    errors: List[SolcOutputError]


class SourceUnitInfo(BuildInfoModel):
    """
    Attributes:
        fs_path: Path to the source unit.
        blake2b_hash: 256-bit blake2b hash of the source unit contents.
    """

    fs_path: Path
    blake2b_hash: HexBytes


class ProjectBuildInfo(BuildInfoModel):
    """
    Attributes:
        compilation_units: Mapping of compilation unit hex-encoded hashes to compilation unit build info.
        source_units_info: Mapping of source unit names to source unit info.
        allow_paths: Compilation [allow_paths][wake.config.data_model.SolcConfig.allow_paths] used during compilation.
        exclude_paths: Compilation [exclude_paths][wake.config.data_model.SolcConfig.exclude_paths] used during compilation.
        include_paths: Compilation [include_paths][wake.config.data_model.SolcConfig.include_paths] used during compilation.
        settings: solc input settings used during compilation.
        target_solidity_version: Solidity [target_version][wake.config.data_model.SolcConfig.target_version] used during compilation, if any.
        wake_version: `eth-wake` version used during compilation.
        incremental: Whether the compilation was performed in incremental mode.
    """

    compilation_units: Dict[str, CompilationUnitBuildInfo]
    source_units_info: Dict[str, SourceUnitInfo]
    allow_paths: FrozenSet[PurePath]
    exclude_paths: FrozenSet[PurePath]
    include_paths: FrozenSet[PurePath]
    settings: Dict[Optional[str], SolcInputSettings]
    target_solidity_versions: Dict[Optional[str], Optional[SolidityVersion]]
    wake_version: str
    incremental: bool

    @field_serializer("settings", when_used="json")
    def serialize_settings(
        self, settings: Dict[Optional[str], SolcInputSettings], info
    ):
        return {k if k is not None else "__null__": v for k, v in settings.items()}

    @field_validator("settings", mode="before")
    def validate_settings(cls, v: Dict[Optional[str], SolcInputSettings], info: Any):
        if "__null__" in v:
            v[None] = v.pop("__null__")
        return v

    @field_serializer("target_solidity_versions", when_used="json")
    def serialize_target_versions(
        self, versions: Dict[Optional[str], Optional[SolidityVersion]], info
    ):
        return {
            k if k is not None else "__null__": str(v) if v is not None else None
            for k, v in versions.items()
        }

    @field_validator("target_solidity_versions", mode="before")
    def validate_target_versions(
        cls, v: Dict[Optional[str], Optional[SolidityVersion]], info: Any
    ):
        if "__null__" in v:
            v[None] = v.pop("__null__")
        return v


class ProjectBuild:
    """
    Class holding a single project build.
    """

    _interval_trees: Dict[Path, IntervalTree]
    _reference_resolver: ReferenceResolver
    _source_units: Dict[Path, SourceUnit]

    def __init__(
        self,
        interval_trees: Dict[Path, IntervalTree],
        reference_resolver: ReferenceResolver,
        source_units: Dict[Path, SourceUnit],
    ):
        self._interval_trees = interval_trees
        self._reference_resolver = reference_resolver
        self._source_units = source_units

    @property
    def interval_trees(self) -> Dict[Path, IntervalTree]:
        """
        Returns:
            Mapping of source file paths to [interval trees](https://github.com/chaimleib/intervaltree) that can be used to query IR nodes by byte offsets in the source code.
        """
        return MappingProxyType(
            self._interval_trees
        )  # pyright: ignore reportGeneralTypeIssues

    @property
    def reference_resolver(self) -> ReferenceResolver:
        """
        Returns:
            Reference resolver responsible for resolving AST node IDs to IR nodes. Useful especially for resolving references across different compilation units.
        """
        return self._reference_resolver

    @property
    def source_units(self) -> Dict[Path, SourceUnit]:
        """
        Returns:
            Mapping of source file paths to top-level [SourceUnit][wake.ir.meta.source_unit.SourceUnit] IR nodes.
        """
        return MappingProxyType(
            self._source_units
        )  # pyright: ignore reportGeneralTypeIssues

    def fix_after_deserialization(self, lsp: bool):
        """
        Fix the internal state of the project build after pickle deserialization.
        """
        if lsp:
            for source_unit in self._source_units.values():
                for node in source_unit:
                    if isinstance(node, SolidityAbc):
                        self._reference_resolver.register_node(node, node.ast_node_id, source_unit.cu_hash)

        for source_unit in self._source_units.values():
            source_unit._parent = None
            inline_assembly = None

            for node in source_unit:
                r = weakref.ref(node)
                for child in node.children:
                    child._parent = r

                node._source_unit = weakref.ref(source_unit)
                node._reference_resolver = weakref.proxy(self._reference_resolver)

                if isinstance(node, InlineAssembly):
                    inline_assembly = node

                    for external_ref in node.external_references:
                        external_ref._inline_assembly = weakref.ref(inline_assembly)
                        external_ref._source_unit = weakref.ref(source_unit)
                        external_ref._reference_resolver = weakref.proxy(
                            self._reference_resolver
                        )

                        external_ref.referenced_declaration.register_reference(
                            external_ref
                        )
                elif isinstance(node, (IdentifierPath, UserDefinedTypeName)):
                    for part in node.identifier_path_parts:
                        part._underlying_node = weakref.ref(node)
                        part._source_unit = weakref.ref(source_unit)
                        part._reference_resolver = weakref.proxy(
                            self._reference_resolver
                        )

                        ref_decl = part.referenced_declaration
                        if isinstance(ref_decl, DeclarationAbc):
                            ref_decl.register_reference(part)
                elif isinstance(node, (Identifier, MemberAccess)):
                    ref_decl = node.referenced_declaration
                    if isinstance(ref_decl, DeclarationAbc):
                        ref_decl.register_reference(node)
                    elif isinstance(ref_decl, set):
                        for d in ref_decl:
                            d.register_reference(node)

                    if lsp and isinstance(ref_decl, GlobalSymbol):
                        self._reference_resolver.register_global_symbol_reference(ref_decl, node)
                elif isinstance(node, (BinaryOperation, UnaryOperation)):
                    if node.function is not None:
                        node.function.register_reference(node)
                elif isinstance(node, YulAbc):
                    node._inline_assembly = weakref.ref(inline_assembly)

                    if isinstance(node, YulIdentifier):
                        external_ref = next(
                            (
                                r
                                for r in inline_assembly.external_references
                                if r.yul_identifier == node
                            ),
                            None,
                        )
                        node._external_reference = (
                            weakref.ref(external_ref)
                            if external_ref is not None
                            else None
                        )
                elif isinstance(node, ModifierDefinition):
                    for base_modifier in node.base_modifiers:
                        base_modifier._child_modifiers.add(weakref.ref(node))
                elif isinstance(node, FunctionDefinition):
                    for base_function in node.base_functions:
                        base_function._child_functions.add(weakref.ref(node))
                elif isinstance(node, VariableDeclaration):
                    for base_function in node.base_functions:
                        base_function._child_functions.add(weakref.ref(node))
                elif isinstance(node, ContractDefinition):
                    for event_id in node._used_event_ids:
                        # use event ids to avoid double iteration
                        event = self._reference_resolver.resolve_node(
                            event_id, source_unit.cu_hash
                        )
                        assert isinstance(event, EventDefinition)
                        event._used_in.add(weakref.ref(node))
                        node._used_events.add(weakref.ref(event))

                    for error in node.used_errors:
                        error._used_in.add(weakref.ref(node))

                    for base_contract in node.base_contracts:
                        # cannot use base_contract.base_name.referenced_declaration because reference_resolver is not yet fixed
                        c = self._reference_resolver.resolve_node(
                            base_contract.base_name._referenced_declaration_id,
                            source_unit.cu_hash,
                        )
                        assert isinstance(c, ContractDefinition)
                        c._child_contracts.add(weakref.ref(node))
