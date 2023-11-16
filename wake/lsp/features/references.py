import logging
from typing import List, Union

from wake.core import get_logger
from wake.ir import (
    BinaryOperation,
    DeclarationAbc,
    ExternalReference,
    Identifier,
    IdentifierPath,
    IdentifierPathPart,
    IrAbc,
    MemberAccess,
    UnaryOperation,
    UserDefinedTypeName,
    YulIdentifier,
)
from wake.ir.enums import GlobalSymbol
from wake.lsp.common_structures import (
    DocumentUri,
    Location,
    PartialResultParams,
    TextDocumentPositionParams,
    TextDocumentRegistrationOptions,
    WorkDoneProgressOptions,
    WorkDoneProgressParams,
)
from wake.lsp.context import LspContext
from wake.lsp.lsp_data_model import LspModel
from wake.lsp.utils import path_to_uri, position_within_range, uri_to_path

logger = get_logger(__name__)


class ReferenceOptions(WorkDoneProgressOptions):
    pass


class ReferenceRegistrationOptions(TextDocumentRegistrationOptions, ReferenceOptions):
    pass


class ReferenceContext(LspModel):
    include_declaration: bool


class ReferenceParams(
    TextDocumentPositionParams, WorkDoneProgressParams, PartialResultParams
):
    context: ReferenceContext


def _generate_reference_location(
    reference: Union[
        Identifier,
        IdentifierPathPart,
        MemberAccess,
        ExternalReference,
        UnaryOperation,
        BinaryOperation,
        DeclarationAbc,
    ],
    context: LspContext,
) -> Location:
    path = reference.source_unit.file
    if isinstance(reference, MemberAccess):
        location = reference.member_location
    elif isinstance(reference, ExternalReference):
        location = reference.identifier_location
    elif isinstance(reference, DeclarationAbc):
        location = reference.name_location
    else:
        location = reference.byte_location

    return Location(
        uri=DocumentUri(path_to_uri(path)),
        range=context.compiler.get_range_from_byte_offsets(path, location),
    )


async def references(
    context: LspContext, params: ReferenceParams
) -> Union[List[Location], None]:
    logger.debug(
        f"References for file {params.text_document.uri} at position {params.position} requested"
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
        referenced_declaration = node.referenced_declaration
        if referenced_declaration is None:
            return None
        if isinstance(referenced_declaration, GlobalSymbol):
            global_refs = (
                context.compiler.ir_reference_resolver.get_global_symbol_references(
                    referenced_declaration
                )
            )
            if len(global_refs) > 0:
                return [
                    _generate_reference_location(ref, context) for ref in global_refs
                ]
            return None
        else:
            node = referenced_declaration
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
    elif (
        isinstance(node, (UnaryOperation, BinaryOperation))
        and node.function is not None
    ):
        node = node.function

    if not isinstance(node, (DeclarationAbc, set)):
        return None

    refs = []
    if isinstance(node, set):
        for n in node:
            assert isinstance(n, DeclarationAbc)
            for reference in n.get_all_references(
                context.config.lsp.find_references.include_declarations
            ):
                refs.append(_generate_reference_location(reference, context))
    else:
        for reference in node.get_all_references(
            context.config.lsp.find_references.include_declarations
        ):
            refs.append(_generate_reference_location(reference, context))

    if len(refs) == 0:
        return None
    return refs
