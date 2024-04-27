import logging
from typing import List, Optional, Union

from wake.core import get_logger
from wake.ir import (
    ContractDefinition,
    DeclarationAbc,
    FunctionDefinition,
    Identifier,
    IdentifierPath,
    IrAbc,
    MemberAccess,
    ModifierDefinition,
    UserDefinedTypeName,
    VariableDeclaration,
    YulIdentifier,
)
from wake.ir.ast import AstNodeId
from wake.ir.enums import ContractKind
from wake.lsp.common_structures import (
    DocumentUri,
    PartialResultParams,
    Range,
    StaticRegistrationOptions,
    SymbolKind,
    SymbolTag,
    TextDocumentPositionParams,
    TextDocumentRegistrationOptions,
    WorkDoneProgressOptions,
    WorkDoneProgressParams,
)
from wake.lsp.context import LspContext
from wake.lsp.lsp_data_model import LspModel
from wake.lsp.utils import path_to_uri, position_within_range, uri_to_path

logger = get_logger(__name__)


class TypeHierarchyOptions(WorkDoneProgressOptions):
    pass


class TypeHierarchyRegistrationOptions(
    TextDocumentRegistrationOptions, TypeHierarchyOptions, StaticRegistrationOptions
):
    pass


class TypeHierarchyPrepareParams(TextDocumentPositionParams, WorkDoneProgressParams):
    pass


class TypeHierarchyItemData(LspModel):
    ast_node_id: int
    cu_hash: str
    uri: DocumentUri


class TypeHierarchyItem(LspModel):
    name: str
    """
    The name of this item.
    """
    kind: SymbolKind
    """
    The kind of this item.
    """
    tags: Optional[List[SymbolTag]] = None
    """
    Tags for this item.
    """
    detail: Optional[str] = None
    """
    More detail for this item, e.g. the signature of a function.
    """
    uri: DocumentUri
    """
    The resource identifier of this item.
    """
    range: Range
    """
    The range enclosing this symbol not including leading/trailing whitespace
    but everything else, e.g. comments and code.
    """
    selection_range: Range
    """
    The range that should be selected and revealed when this symbol is being
    picked, e.g. the name of a function. Muse be contained by the
    [`range`](#TypeHierarchyItem.range).
    """
    data: TypeHierarchyItemData
    """
    A data entry field that is preserved between a type hierarchy prepare and
    supertypes or subtypes requests. It could also be used to identify the
    type hierarchy in the server, helping improve the performance on
    resolving supertypes and subtypes.
    """


class TypeHierarchySupertypesParams(WorkDoneProgressParams, PartialResultParams):
    item: TypeHierarchyItem


class TypeHierarchySubtypesParams(WorkDoneProgressParams, PartialResultParams):
    item: TypeHierarchyItem


def _get_node_symbol_kind(
    node: Union[
        ContractDefinition, FunctionDefinition, ModifierDefinition, VariableDeclaration
    ]
) -> SymbolKind:
    if isinstance(node, ContractDefinition):
        if node.kind == ContractKind.CONTRACT:
            return SymbolKind.CLASS
        elif node.kind == ContractKind.INTERFACE:
            return SymbolKind.INTERFACE
        elif node.kind == ContractKind.LIBRARY:
            return SymbolKind.MODULE
        else:
            assert False, f"Unknown contract kind {node.kind}"
    elif isinstance(node, FunctionDefinition):
        if isinstance(node.parent, ContractDefinition):
            return SymbolKind.METHOD
        else:
            return SymbolKind.FUNCTION
    elif isinstance(node, ModifierDefinition):
        return SymbolKind.FUNCTION
    elif isinstance(node, VariableDeclaration):
        return SymbolKind.VARIABLE
    else:
        assert False, f"Unknown node type {type(node)}"


def prepare_type_hierarchy_item(
    context: LspContext,
    node: Union[
        ContractDefinition, FunctionDefinition, ModifierDefinition, VariableDeclaration
    ],
) -> TypeHierarchyItem:
    return TypeHierarchyItem(
        name=node.canonical_name,
        kind=_get_node_symbol_kind(node),
        tags=None,
        detail=None,
        uri=DocumentUri(path_to_uri(node.source_unit.file)),
        range=context.compiler.get_range_from_byte_offsets(
            node.source_unit.file, node.byte_location
        ),
        selection_range=context.compiler.get_range_from_byte_offsets(
            node.source_unit.file, node.name_location
        ),
        data=TypeHierarchyItemData(
            ast_node_id=node.ast_node_id,
            cu_hash=node.source_unit.cu_hash.hex(),
            uri=DocumentUri(path_to_uri(node.source_unit.file)),
        ),
    )


async def prepare_type_hierarchy(
    context: LspContext, params: TypeHierarchyPrepareParams
) -> Union[List[TypeHierarchyItem], None]:
    logger.debug(
        f"Type hierarchy for file {params.text_document.uri} at position {params.position} requested"
    )
    await context.compiler.output_ready.wait()

    path = uri_to_path(params.text_document.uri).resolve()

    if path not in context.compiler.interval_trees:
        return None

    tree = context.compiler.interval_trees[path]

    byte_offset = context.compiler.get_byte_offset_from_line_pos(
        path, params.position.line, params.position.character
    )
    intervals = tree.at(byte_offset)
    nodes: List[IrAbc] = [interval.data for interval in intervals]
    logger.debug(
        f"Found {len(nodes)} nodes at byte offset {byte_offset}:\n{sorted(nodes, key=lambda x: x.ast_tree_depth)}"
    )
    if len(nodes) == 0:
        return None

    node = max(nodes, key=lambda n: n.ast_tree_depth)
    logger.debug(f"Found node {node}")

    if isinstance(node, DeclarationAbc):
        name_location_range = context.compiler.get_range_from_byte_offsets(
            node.source_unit.file, node.name_location
        )
        if not position_within_range(params.position, name_location_range):
            return None

    if isinstance(node, (Identifier, MemberAccess)):
        node = node.referenced_declaration
    elif isinstance(node, (IdentifierPath, UserDefinedTypeName)):
        part = node.identifier_path_part_at(byte_offset)
        if part is None:
            return None
        node = part.referenced_declaration
    elif isinstance(node, YulIdentifier):
        external_reference = node.external_reference
        if external_reference is None:
            return None
        node = external_reference.referenced_declaration

    if isinstance(
        node, (ContractDefinition, FunctionDefinition, ModifierDefinition)
    ) or (isinstance(node, VariableDeclaration) and node.overrides is not None):
        return [prepare_type_hierarchy_item(context, node)]
    elif isinstance(node, set):
        return [
            prepare_type_hierarchy_item(
                context, n  # pyright: ignore reportGeneralTypeIssues
            )
            for n in node
        ]

    return None


async def supertypes(
    context: LspContext, params: TypeHierarchySupertypesParams
) -> Union[List[TypeHierarchyItem], None]:
    logger.debug(f"Supertypes for {params.item} requested")
    ast_node_id = params.item.data.ast_node_id
    cu_hash = bytes.fromhex(params.item.data.cu_hash)
    node = context.compiler.ir_reference_resolver.resolve_node(
        AstNodeId(ast_node_id), cu_hash
    )
    assert isinstance(
        node,
        (
            ContractDefinition,
            FunctionDefinition,
            ModifierDefinition,
            VariableDeclaration,
        ),
    )

    type_items = []
    nodes: List[
        Union[
            ContractDefinition,
            FunctionDefinition,
            ModifierDefinition,
            VariableDeclaration,
        ]
    ] = []
    if isinstance(node, ContractDefinition):
        for base_contract in node.base_contracts:
            contract = base_contract.base_name.referenced_declaration
            assert isinstance(contract, ContractDefinition)
            nodes.append(contract)
    elif isinstance(node, (FunctionDefinition, VariableDeclaration)):
        for base_function in node.base_functions:
            nodes.append(base_function)
    elif isinstance(node, ModifierDefinition):
        for base_modifier in node.base_modifiers:
            nodes.append(base_modifier)

    for node in nodes:
        type_items.append(
            TypeHierarchyItem(
                name=node.canonical_name,
                kind=_get_node_symbol_kind(node),
                tags=None,
                detail=None,
                uri=DocumentUri(path_to_uri(node.source_unit.file)),
                range=context.compiler.get_range_from_byte_offsets(
                    node.source_unit.file, node.byte_location
                ),
                selection_range=context.compiler.get_range_from_byte_offsets(
                    node.source_unit.file, node.name_location
                ),
                data=TypeHierarchyItemData(
                    ast_node_id=node.ast_node_id,
                    cu_hash=node.source_unit.cu_hash.hex(),
                    uri=DocumentUri(path_to_uri(node.source_unit.file)),
                ),
            )
        )
    return type_items


async def subtypes(
    context: LspContext, params: TypeHierarchySubtypesParams
) -> Union[List[TypeHierarchyItem], None]:
    logger.debug(f"Subtypes for {params.item} requested")
    ast_node_id = params.item.data.ast_node_id
    cu_hash = bytes.fromhex(params.item.data.cu_hash)
    node = context.compiler.ir_reference_resolver.resolve_node(
        AstNodeId(ast_node_id), cu_hash
    )
    assert isinstance(
        node,
        (
            ContractDefinition,
            FunctionDefinition,
            ModifierDefinition,
            VariableDeclaration,
        ),
    )

    type_items = []
    nodes: List[
        Union[
            ContractDefinition,
            FunctionDefinition,
            ModifierDefinition,
            VariableDeclaration,
        ]
    ] = []
    if isinstance(node, ContractDefinition):
        for child_contract in node.child_contracts:
            nodes.append(child_contract)
    elif isinstance(node, FunctionDefinition) and node.child_functions:
        for child_function in node.child_functions:
            nodes.append(child_function)
    elif isinstance(node, ModifierDefinition):
        for child_modifier in node.child_modifiers:
            nodes.append(child_modifier)

    for node in nodes:
        type_items.append(
            TypeHierarchyItem(
                name=node.canonical_name,
                kind=_get_node_symbol_kind(node),
                tags=None,
                detail=None,
                uri=DocumentUri(path_to_uri(node.source_unit.file)),
                range=context.compiler.get_range_from_byte_offsets(
                    node.source_unit.file, node.byte_location
                ),
                selection_range=context.compiler.get_range_from_byte_offsets(
                    node.source_unit.file, node.name_location
                ),
                data=TypeHierarchyItemData(
                    ast_node_id=node.ast_node_id,
                    cu_hash=node.source_unit.cu_hash.hex(),
                    uri=DocumentUri(path_to_uri(node.source_unit.file)),
                ),
            )
        )
    return type_items
