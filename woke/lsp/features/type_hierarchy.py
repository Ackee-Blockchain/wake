import logging
from typing import Any, List, Optional, Union

from woke.ast.enums import ContractKind
from woke.ast.ir.abc import IrAbc
from woke.ast.ir.declaration.contract_definition import ContractDefinition
from woke.ast.ir.expression.identifier import Identifier
from woke.ast.ir.meta.identifier_path import IdentifierPath
from woke.ast.ir.type_name.user_defined_type_name import UserDefinedTypeName
from woke.ast.nodes import AstNodeId
from woke.lsp.common_structures import (
    DocumentUri,
    PartialResultParams,
    Position,
    Range,
    StaticRegistrationOptions,
    SymbolKind,
    SymbolTag,
    TextDocumentPositionParams,
    TextDocumentRegistrationOptions,
    WorkDoneProgressOptions,
    WorkDoneProgressParams,
)
from woke.lsp.context import LspContext
from woke.lsp.lsp_data_model import LspModel
from woke.lsp.utils.uri import path_to_uri, uri_to_path

logger = logging.getLogger(__name__)


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


class TypeHierarchyItem(LspModel):
    name: str
    """
    The name of this item.
    """
    kind: SymbolKind
    """
    The kind of this item.
    """
    tags: Optional[List[SymbolTag]]
    """
    Tags for this item.
    """
    detail: Optional[str]
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


def prepare_type_hierarchy(
    context: LspContext, params: TypeHierarchyPrepareParams
) -> Union[List[TypeHierarchyItem], None]:
    logger.debug(
        f"Type hierarchy for file {params.text_document.uri} at position {params.position} requested"
    )

    path = uri_to_path(params.text_document.uri).resolve()

    if path not in context.compiler.interval_trees:
        return None

    tree = context.compiler.interval_trees[path]

    byte_offset = context.compiler.get_byte_offset_from_line_pos(
        path, params.position.line, params.position.character
    )
    intervals = tree.at(byte_offset)
    nodes: List[IrAbc] = [interval.data for interval in intervals]
    logger.debug(f"Found {len(nodes)} nodes at byte offset {byte_offset}:\n{nodes}")

    node = max(nodes, key=lambda n: n.ast_tree_depth)
    logger.debug(f"Found node {node}")

    if (
        isinstance(node, IdentifierPath)
        or isinstance(node, UserDefinedTypeName)
        or isinstance(node, Identifier)
    ):
        node = node.referenced_declaration
        logger.debug(f"Found referenced declaration {node}")

    if isinstance(node, ContractDefinition):
        name_byte_start, name_byte_end = node.name_location
        (
            name_start_line,
            name_start_column,
        ) = context.compiler.get_line_pos_from_byte_offset(path, name_byte_start)
        name_end_line, name_end_column = context.compiler.get_line_pos_from_byte_offset(
            path, name_byte_end
        )

        if node.kind == ContractKind.CONTRACT:
            kind = SymbolKind.CLASS
        elif node.kind == ContractKind.INTERFACE:
            kind = SymbolKind.INTERFACE
        elif node.kind == ContractKind.LIBRARY:
            kind = SymbolKind.MODULE
        else:
            assert False, f"Unknown contract kind {node.kind}"

        return [
            TypeHierarchyItem(
                name=node.name,
                kind=kind,
                tags=None,
                detail=None,
                uri=DocumentUri(path_to_uri(node.file)),
                range=Range(
                    start=Position(line=name_start_line, character=name_start_column),
                    end=Position(line=name_end_line, character=name_end_column),
                ),
                selection_range=Range(
                    start=Position(line=name_start_line, character=name_start_column),
                    end=Position(line=name_end_line, character=name_end_column),
                ),
                data=TypeHierarchyItemData(
                    ast_node_id=node.ast_node_id, cu_hash=node.cu_hash.hex()
                ),
            )
        ]

    return None


def supertypes(
    context: LspContext, params: TypeHierarchySupertypesParams
) -> Union[List[TypeHierarchyItem], None]:
    logger.debug(f"Supertypes for {params.item} requested")
    ast_node_id = params.item.data.ast_node_id
    cu_hash = bytes.fromhex(params.item.data.cu_hash)
    node = context.compiler.ir_reference_resolver.resolve_node(
        AstNodeId(ast_node_id), cu_hash
    )
    assert isinstance(node, ContractDefinition)

    type_items = []

    for base_contract in node.base_contracts:
        contract = base_contract.base_name.referenced_declaration
        assert isinstance(contract, ContractDefinition)

        name_byte_start, name_byte_end = contract.name_location
        (
            name_start_line,
            name_start_column,
        ) = context.compiler.get_line_pos_from_byte_offset(
            contract.file, name_byte_start
        )
        name_end_line, name_end_column = context.compiler.get_line_pos_from_byte_offset(
            contract.file, name_byte_end
        )
        if contract.kind == ContractKind.CONTRACT:
            kind = SymbolKind.CLASS
        elif contract.kind == ContractKind.INTERFACE:
            kind = SymbolKind.INTERFACE
        elif contract.kind == ContractKind.LIBRARY:
            kind = SymbolKind.MODULE
        else:
            assert False, f"Unknown contract kind {contract.kind}"

        type_items.append(
            TypeHierarchyItem(
                name=contract.name,
                kind=kind,
                tags=None,
                detail=None,
                uri=DocumentUri(path_to_uri(contract.file)),
                range=Range(
                    start=Position(line=name_start_line, character=name_start_column),
                    end=Position(line=name_end_line, character=name_end_column),
                ),
                selection_range=Range(
                    start=Position(line=name_start_line, character=name_start_column),
                    end=Position(line=name_end_line, character=name_end_column),
                ),
                data=TypeHierarchyItemData(
                    ast_node_id=contract.ast_node_id, cu_hash=contract.cu_hash.hex()
                ),
            )
        )
    return type_items


def subtypes(
    context: LspContext, params: TypeHierarchySubtypesParams
) -> Union[List[TypeHierarchyItem], None]:
    logger.debug(f"Subtypes for {params.item} requested")
    ast_node_id = params.item.data.ast_node_id
    cu_hash = bytes.fromhex(params.item.data.cu_hash)
    node = context.compiler.ir_reference_resolver.resolve_node(
        AstNodeId(ast_node_id), cu_hash
    )
    assert isinstance(node, ContractDefinition)

    type_items = []
    for contract in node.child_contracts:
        name_byte_start, name_byte_end = contract.name_location
        (
            name_start_line,
            name_start_column,
        ) = context.compiler.get_line_pos_from_byte_offset(
            contract.file, name_byte_start
        )
        name_end_line, name_end_column = context.compiler.get_line_pos_from_byte_offset(
            contract.file, name_byte_end
        )
        if contract.kind == ContractKind.CONTRACT:
            kind = SymbolKind.CLASS
        elif contract.kind == ContractKind.INTERFACE:
            kind = SymbolKind.INTERFACE
        elif contract.kind == ContractKind.LIBRARY:
            kind = SymbolKind.MODULE
        else:
            assert False, f"Unknown contract kind {contract.kind}"

        type_items.append(
            TypeHierarchyItem(
                name=contract.name,
                kind=kind,
                tags=None,
                detail=None,
                uri=DocumentUri(path_to_uri(contract.file)),
                range=Range(
                    start=Position(line=name_start_line, character=name_start_column),
                    end=Position(line=name_end_line, character=name_end_column),
                ),
                selection_range=Range(
                    start=Position(line=name_start_line, character=name_start_column),
                    end=Position(line=name_end_line, character=name_end_column),
                ),
                data=TypeHierarchyItemData(
                    ast_node_id=contract.ast_node_id, cu_hash=contract.cu_hash.hex()
                ),
            )
        )
    return type_items
