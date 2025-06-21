import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import DefaultDict, List, Optional, Set, Tuple, Union

from wake.core import get_logger
from wake.ir import (
    BinaryOperation,
    DeclarationAbc,
    EnumDefinition,
    EnumValue,
    ExternalReference,
    FunctionDefinition,
    Identifier,
    IdentifierPath,
    IdentifierPathPart,
    IrAbc,
    MemberAccess,
    ParameterList,
    StructDefinition,
    UnaryOperation,
    UserDefinedTypeName,
    VariableDeclaration,
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


def _find_nearest_comment_blocks(declaration: DeclarationAbc) -> List[Tuple[int, int]]:
    """
    Find the nearest NatSpec comment blocks immediately preceding the declaration.

    Returns:
        List of (start_byte_offset, end_byte_offset) tuples for comment blocks.
    """
    source_code = declaration.source_unit.file_source
    declaration_start = declaration.byte_location[0]
    code_before_declaration = source_code[:declaration_start]
    code_str = code_before_declaration.decode("utf-8", errors="ignore")

    comment_blocks = []

    # Function to check if all non-comment content after `end` is only whitespace
    def is_followed_only_by_whitespace(end_pos: int) -> bool:
        return code_str[end_pos:].strip() == ""

    # Match /// comments
    single_line_pattern = r"(///[^\n]*\n?)+"
    single_line_matches = list(re.finditer(single_line_pattern, code_str))
    for i in reversed(range(len(single_line_matches))):
        match = single_line_matches[i]
        if is_followed_only_by_whitespace(match.end()):
            comment_blocks.insert(0, (match.start(), match.end()))
            # Continue collecting consecutive comment blocks backwards
            current_end = match.start()
            for j in range(i - 1, -1, -1):
                prev_match = single_line_matches[j]
                between = code_str[prev_match.end() : current_end]
                if between.strip() == "":
                    comment_blocks.insert(0, (prev_match.start(), prev_match.end()))
                    current_end = prev_match.start()
                else:
                    break
            break  # Stop after collecting the nearest block

    # Match /** */ style comments
    multi_line_pattern = r"/\*\*.*?\*/"
    multi_line_matches = list(re.finditer(multi_line_pattern, code_str, re.DOTALL))
    if multi_line_matches:
        last = multi_line_matches[-1]
        if is_followed_only_by_whitespace(last.end()):
            comment_blocks.append((last.start(), last.end()))

    return comment_blocks


def _find_natspec_patterns_in_comments(
    comment_blocks: List[Tuple[int, int]], declaration_name: str, source_code: bytes
) -> List[Tuple[int, int]]:
    """
    Search for @param and @return references to the declaration name within comment blocks.

    Args:
        comment_blocks: List of (start_byte_offset, end_byte_offset) tuples for comment blocks
        declaration_name: Name of the declaration to search for
        source_code: Full source code as bytes

    Returns:
        List of (start_byte_offset, end_byte_offset) tuples for NatSpec references
    """
    natspec_references = []
    code_str = source_code.decode("utf-8", errors="ignore")

    # Pattern to match @param and @return tags followed by the declaration name
    # Capture only the declaration name part, not the entire tag
    param_pattern = rf"@param\s+({re.escape(declaration_name)})\b"
    return_pattern = rf"@return\s+({re.escape(declaration_name)})\b"

    for comment_start, comment_end in comment_blocks:
        comment_text = code_str[comment_start:comment_end]

        # Check for @param references
        param_matches = re.finditer(param_pattern, comment_text)
        for param_match in param_matches:
            # Use the captured group (the declaration name only)
            param_start = comment_start + param_match.start(1)
            param_end = comment_start + param_match.end(1)
            natspec_references.append((param_start, param_end))

        # Check for @return references
        return_matches = re.finditer(return_pattern, comment_text)
        for return_match in return_matches:
            # Use the captured group (the declaration name only)
            return_start = comment_start + return_match.start(1)
            return_end = comment_start + return_match.end(1)
            natspec_references.append((return_start, return_end))

    return natspec_references


def _find_natspec_references(declaration: DeclarationAbc) -> List[Tuple[int, int]]:
    """
    Find all NatSpec @param and @return references to the declaration name
    in the nearest comment blocks preceding the declaration.

    Returns:
        List of (start_byte_offset, end_byte_offset) tuples for NatSpec references
    """
    source_code = declaration.source_unit.file_source
    declaration_name = declaration.name

    if (
        isinstance(declaration, VariableDeclaration)
        and isinstance(declaration.parent, ParameterList)
        and isinstance(declaration.parent.parent, DeclarationAbc)
    ):
        declaration = declaration.parent.parent
    elif isinstance(declaration, VariableDeclaration) and isinstance(
        declaration.parent, StructDefinition
    ):
        declaration = declaration.parent
    elif isinstance(declaration, EnumValue) and isinstance(
        declaration.parent, EnumDefinition
    ):
        declaration = declaration.parent
    else:
        return []

    # Find the nearest comment blocks
    comment_blocks = _find_nearest_comment_blocks(declaration)

    # Search for NatSpec patterns within those comments
    return _find_natspec_patterns_in_comments(
        comment_blocks, declaration_name, source_code
    )


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
            for natspec_offsets in _find_natspec_references(func):
                changes_by_file[func.source_unit.file].append(
                    TextEdit(
                        range=context.compiler.get_range_from_byte_offsets(
                            func.source_unit.file, natspec_offsets
                        ),
                        new_text=new_name,
                    )
                )
    else:
        all_references.update(declaration.get_all_references(True))
        for natspec_offsets in _find_natspec_references(declaration):
            changes_by_file[declaration.source_unit.file].append(
                TextEdit(
                    range=context.compiler.get_range_from_byte_offsets(
                        declaration.source_unit.file, natspec_offsets
                    ),
                    new_text=new_name,
                )
            )

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

    logger.debug(f"Waiting for compiler")

    await context.compiler.compilation_ready.wait()

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

    await context.compiler.compilation_ready.wait()

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
