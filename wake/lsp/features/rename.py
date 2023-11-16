import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import DefaultDict, List, Optional, Set, Union

from wake.core import get_logger
from wake.ir import (
    BinaryOperation,
    DeclarationAbc,
    ExternalReference,
    FunctionDefinition,
    Identifier,
    IdentifierPath,
    IdentifierPathPart,
    IrAbc,
    MemberAccess,
    UnaryOperation,
    UserDefinedTypeName,
    YulIdentifier,
)
from wake.lsp.common_structures import (
    DocumentUri,
    OptionalVersionedTextDocumentIdentifier,
    Range,
    TextDocumentEdit,
    TextDocumentPositionParams,
    TextDocumentRegistrationOptions,
    TextEdit,
    WorkDoneProgressOptions,
    WorkDoneProgressParams,
    WorkspaceEdit,
)
from wake.lsp.context import LspContext
from wake.lsp.exceptions import LspError
from wake.lsp.protocol_structures import ErrorCodes
from wake.lsp.utils import path_to_uri, position_within_range, uri_to_path

logger = get_logger(__name__)


class RenameOptions(WorkDoneProgressOptions):
    prepare_provider: Optional[bool]
    """
    Renames should be checked and tested before being executed.
    """


class RenameRegistrationOptions(TextDocumentRegistrationOptions, RenameOptions):
    pass


class RenameParams(TextDocumentPositionParams, WorkDoneProgressParams):
    new_name: str
    """
    The new name of the symbol. If the given name is not valid the
    request must return a [ResponseError](#ResponseError) with an
    appropriate message set.
    """


class PrepareRenameParams(TextDocumentPositionParams, WorkDoneProgressParams):
    pass


def _generate_reference_location(
    reference: Union[
        Identifier,
        IdentifierPathPart,
        MemberAccess,
        ExternalReference,
        DeclarationAbc,
    ],
    context: LspContext,
) -> Range:
    path = reference.source_unit.file
    if isinstance(reference, MemberAccess):
        location = reference.member_location
    elif isinstance(reference, ExternalReference):
        location = reference.identifier_location
    elif isinstance(reference, DeclarationAbc):
        location = reference.name_location
    else:
        location = reference.byte_location
    return context.compiler.get_range_from_byte_offsets(path, location)


def _generate_workspace_edit(
    declaration: Union[DeclarationAbc, Set[FunctionDefinition]],
    new_name: str,
    context: LspContext,
) -> WorkspaceEdit:
    changes_by_file: DefaultDict[Path, List[TextEdit]] = defaultdict(list)

    all_references = set()
    if isinstance(declaration, set):
        for func in declaration:
            all_references.update(func.get_all_references(True))
    else:
        all_references.update(declaration.get_all_references(True))

    for reference in all_references:
        if not isinstance(reference, (UnaryOperation, BinaryOperation)):
            changes_by_file[reference.source_unit.file].append(
                TextEdit(
                    range=_generate_reference_location(reference, context),
                    new_text=new_name,
                )
            )

    changes: DefaultDict[DocumentUri, List[TextEdit]] = defaultdict(list)
    document_changes = []
    for file, edits in changes_by_file.items():
        changes[DocumentUri(path_to_uri(file))].extend(edits)
        document_changes.append(
            TextDocumentEdit(
                text_document=OptionalVersionedTextDocumentIdentifier(
                    version=context.compiler.get_compiled_file(file).version,
                    uri=DocumentUri(path_to_uri(file)),
                ),
                edits=edits,
            )
        )

    return WorkspaceEdit(
        document_changes=document_changes,
    )


IDENTIFIER_RE = re.compile(r"^[a-zA-Z$_][a-zA-Z0-9$_]*$")


async def rename(
    context: LspContext,
    params: RenameParams,
) -> Union[WorkspaceEdit, None]:
    """
    Renames the symbol denoted by the given text document position.
    """
    logger.debug(
        f"Requested rename for file {params.text_document.uri} at {params.position}"
    )

    match = IDENTIFIER_RE.match(params.new_name)
    if not match:
        raise LspError(ErrorCodes.InvalidRequest, "Invalid identifier name")

    logger.debug(f"Waiting for compiler")

    await context.compiler.output_ready.wait()

    logger.debug(f"Waiting done")

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
        raise LspError(ErrorCodes.RequestFailed, "Cannot rename this symbol")

    node = max(nodes, key=lambda n: n.ast_tree_depth)
    logger.debug(f"Found node {node}")

    if isinstance(node, DeclarationAbc):
        name_location_range = context.compiler.get_range_from_byte_offsets(
            node.source_unit.file, node.name_location
        )
        if not position_within_range(params.position, name_location_range):
            raise LspError(ErrorCodes.RequestFailed, "Cannot rename this symbol")
    elif isinstance(node, Identifier):
        node = node.referenced_declaration
    elif isinstance(node, MemberAccess):
        member_location_range = context.compiler.get_range_from_byte_offsets(
            node.source_unit.file, node.member_location
        )
        if not position_within_range(params.position, member_location_range):
            raise LspError(ErrorCodes.RequestFailed, "Cannot rename this symbol")
        node = node.referenced_declaration
    elif isinstance(node, (IdentifierPath, UserDefinedTypeName)):
        part = node.identifier_path_part_at(byte_offset)
        if part is None:
            raise LspError(ErrorCodes.RequestFailed, "Cannot rename this symbol")
        node = part.referenced_declaration
    elif isinstance(node, YulIdentifier):
        external_reference = node.external_reference
        if external_reference is None:
            raise LspError(ErrorCodes.RequestFailed, "Cannot rename this symbol")
        node = external_reference.referenced_declaration

    if not isinstance(node, (DeclarationAbc, set)):
        raise LspError(ErrorCodes.RequestFailed, "Cannot rename this symbol")

    return _generate_workspace_edit(node, params.new_name, context)


async def prepare_rename(
    context: LspContext,
    params: PrepareRenameParams,
) -> Union[Range, None]:
    """
    Prepares rename.
    """
    logger.debug(
        f"Requested prepare rename for file {params.text_document.uri} at {params.position}"
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

    location = None
    if isinstance(node, Identifier):
        location = node.byte_location
        node = node.referenced_declaration
    elif isinstance(node, MemberAccess):
        location = node.member_location
        node = node.referenced_declaration
    elif isinstance(node, (IdentifierPath, UserDefinedTypeName)):
        part = node.identifier_path_part_at(byte_offset)
        if part is None:
            return None
        location = part.byte_location
        node = part.referenced_declaration
    elif isinstance(node, YulIdentifier):
        external_reference = node.external_reference
        if external_reference is None:
            return None
        location = external_reference.identifier_location
        node = external_reference.referenced_declaration
    elif isinstance(node, DeclarationAbc):
        name_location_range = context.compiler.get_range_from_byte_offsets(
            node.source_unit.file, node.name_location
        )
        if not position_within_range(params.position, name_location_range):
            return None
        location = node.name_location

    if not isinstance(node, (DeclarationAbc, set)) or location is None:
        return None
    return context.compiler.get_range_from_byte_offsets(path, location)
