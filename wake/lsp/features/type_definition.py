import logging
from pathlib import Path
from typing import List, Optional, Tuple, Union

from wake.core import get_logger
from wake.ir import (
    Identifier,
    IdentifierPath,
    IrAbc,
    MemberAccess,
    UserDefinedTypeName,
    VariableDeclaration,
    YulIdentifier,
)
from wake.lsp.common_structures import (
    DocumentUri,
    Location,
    LocationLink,
    PartialResultParams,
    Position,
    StaticRegistrationOptions,
    TextDocumentPositionParams,
    TextDocumentRegistrationOptions,
    WorkDoneProgressOptions,
    WorkDoneProgressParams,
)
from wake.lsp.context import LspContext
from wake.lsp.utils import path_to_uri, position_within_range, uri_to_path
from wake.lsp.utils.position import changes_to_byte_offset

logger = get_logger(__name__)


class TypeDefinitionOptions(WorkDoneProgressOptions):
    pass


class TypeDefinitionRegistrationOptions(
    TextDocumentRegistrationOptions, TypeDefinitionOptions, StaticRegistrationOptions
):
    pass


class TypeDefinitionParams(
    TextDocumentPositionParams, WorkDoneProgressParams, PartialResultParams
):
    pass


def _get_results_from_node(
    original_node: IrAbc,
    position: Position,
    context: LspContext,
    byte_offset: int,
    node_name_location: Optional[Tuple[int, int]],
) -> Optional[List[Tuple[Path, Tuple[int, int]]]]:
    if isinstance(original_node, VariableDeclaration):
        assert node_name_location is not None
        name_location_range = context.compiler.get_range_from_byte_offsets(
            original_node.source_unit.file, node_name_location
        )
        if not position_within_range(position, name_location_range):
            return None

    if isinstance(original_node, (Identifier, MemberAccess)):
        node = original_node.referenced_declaration
        if node is None:
            return None
    elif isinstance(original_node, (IdentifierPath, UserDefinedTypeName)):
        part = original_node.identifier_path_part_at(byte_offset)
        if part is None:
            return None
        node = part.referenced_declaration
    elif isinstance(original_node, YulIdentifier):
        external_reference = original_node.external_reference
        if external_reference is None:
            return None
        node = external_reference.referenced_declaration
    else:
        node = original_node

    if not isinstance(node, VariableDeclaration):
        return None

    type_name = node.type_name
    if isinstance(type_name, UserDefinedTypeName):
        return [
            (
                type_name.referenced_declaration.source_unit.file,
                type_name.referenced_declaration.name_location,
            )
        ]
    else:
        return None


def _get_type_definition_from_cache(
    path: Path,
    position: Position,
    context: LspContext,
):
    new_byte_offset = context.compiler.get_byte_offset_from_line_pos(
        path, position.line, position.character
    )
    backward_changes = context.compiler.get_last_compilation_backward_changes(path)
    if backward_changes is None:
        raise Exception("No backward changes found for path")
    changes_before = backward_changes[0:new_byte_offset]
    old_byte_offset = changes_to_byte_offset(changes_before) + new_byte_offset

    tree = context.compiler.last_compilation_interval_trees[path]

    intervals = tree.at(old_byte_offset)
    nodes: List[IrAbc] = [interval.data for interval in intervals]
    if len(nodes) == 0:
        raise ValueError(f"Could not find node at {old_byte_offset}")

    node = max(nodes, key=lambda n: n.ast_tree_depth)

    if isinstance(node, VariableDeclaration):
        location = node.name_location
        forward_changes = context.compiler.get_last_compilation_forward_changes(path)
        if forward_changes is None:
            raise Exception("No forward changes found for path")
        new_start = (
            changes_to_byte_offset(forward_changes[0 : location[0]]) + location[0]
        )
        new_end = changes_to_byte_offset(forward_changes[0 : location[1]]) + location[1]
        node_name_location = (new_start, new_end)
    else:
        node_name_location = None

    result = _get_results_from_node(
        node, position, context, old_byte_offset, node_name_location
    )
    if result is None:
        return None

    if len(result) == 1:
        path, location = result[0]
        forward_changes = context.compiler.get_last_compilation_forward_changes(path)
        if forward_changes is None:
            raise Exception("No forward changes found for path")
        new_start = (
            changes_to_byte_offset(forward_changes[0 : location[0]]) + location[0]
        )
        new_end = changes_to_byte_offset(forward_changes[0 : location[1]]) + location[1]
        return Location(
            uri=DocumentUri(path_to_uri(path)),
            range=context.compiler.get_range_from_byte_offsets(
                path, (new_start, new_end)
            ),
        )
    else:
        ret = []
        for path, location in result:
            forward_changes = context.compiler.get_last_compilation_forward_changes(
                path
            )
            if forward_changes is None:
                raise Exception("No forward changes found for path")
            new_start = (
                changes_to_byte_offset(forward_changes[0 : location[0]]) + location[0]
            )
            new_end = (
                changes_to_byte_offset(forward_changes[0 : location[1]]) + location[1]
            )
            ret.append(
                Location(
                    uri=DocumentUri(path_to_uri(path)),
                    range=context.compiler.get_range_from_byte_offsets(
                        path, (new_start, new_end)
                    ),
                )
            )
        return ret


async def type_definition(
    context: LspContext, params: TypeDefinitionParams
) -> Union[None, Location, List[Location], List[LocationLink]]:
    logger.debug(
        f"Type definition for file {params.text_document.uri} at position {params.position} requested"
    )

    path = uri_to_path(params.text_document.uri).resolve()
    if (
        path not in context.compiler.interval_trees
        or not context.compiler.output_ready.is_set()
    ):
        # try to use old build artifacts
        try:
            return _get_type_definition_from_cache(path, params.position, context)
        except Exception:
            pass

    await context.compiler.output_ready.wait()
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

    if isinstance(node, VariableDeclaration):
        node_name_location = node.name_location
    else:
        node_name_location = None

    result = _get_results_from_node(
        node, params.position, context, byte_offset, node_name_location
    )
    if result is None:
        return None

    if len(result) == 1:
        path, location = result[0]
        return Location(
            uri=DocumentUri(path_to_uri(path)),
            range=context.compiler.get_range_from_byte_offsets(path, location),
        )
    else:
        return [
            Location(
                uri=DocumentUri(path_to_uri(path)),
                range=context.compiler.get_range_from_byte_offsets(path, location),
            )
            for path, location in result
        ]

    if isinstance(node, VariableDeclaration):
        name_location_range = context.compiler.get_range_from_byte_offsets(
            node.source_unit.file, node.name_location
        )
        if not position_within_range(params.position, name_location_range):
            return None

    if isinstance(node, (Identifier, MemberAccess)):
        node = node.referenced_declaration
        if node is None:
            return None
    elif isinstance(node, (IdentifierPath, UserDefinedTypeName)):
        part = node.identifier_path_part_at(byte_offset)
        if part is None:
            return None
        node = part.referenced_declaration
    elif isinstance(node, yul.Identifier):
        external_reference = node.external_reference
        if external_reference is None:
            return None
        node = external_reference.referenced_declaration

    if not isinstance(node, VariableDeclaration):
        return None

    type_name = node.type_name
    if isinstance(type_name, UserDefinedTypeName):
        return [
            Location(
                uri=DocumentUri(
                    path_to_uri(type_name.referenced_declaration.source_unit.file)
                ),
                range=context.compiler.get_range_from_byte_offsets(
                    type_name.referenced_declaration.source_unit.file,
                    type_name.referenced_declaration.name_location,
                ),
            )
        ]
    else:
        return None
