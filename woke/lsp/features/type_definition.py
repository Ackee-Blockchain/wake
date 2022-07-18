import logging
from typing import List, Union

from woke.ast.ir.abc import IrAbc
from woke.ast.ir.declaration.variable_declaration import VariableDeclaration
from woke.ast.ir.expression.identifier import Identifier
from woke.ast.ir.expression.member_access import MemberAccess
from woke.ast.ir.meta.identifier_path import IdentifierPath
from woke.ast.ir.statement.inline_assembly import InlineAssembly
from woke.ast.ir.type_name.user_defined_type_name import UserDefinedTypeName
from woke.lsp.common_structures import (
    DocumentUri,
    Location,
    LocationLink,
    PartialResultParams,
    StaticRegistrationOptions,
    TextDocumentPositionParams,
    TextDocumentRegistrationOptions,
    WorkDoneProgressOptions,
    WorkDoneProgressParams,
)
from woke.lsp.context import LspContext
from woke.lsp.utils import path_to_uri, position_within_range, uri_to_path

logger = logging.getLogger(__name__)


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


async def type_definition(
    context: LspContext, params: TypeDefinitionParams
) -> Union[None, Location, List[Location], List[LocationLink]]:
    logger.debug(
        f"Type definition for file {params.text_document.uri} at position {params.position} requested"
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

    if isinstance(node, VariableDeclaration):
        name_location_range = context.compiler.get_range_from_byte_offsets(
            node.file, node.name_location
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
    elif isinstance(node, InlineAssembly):
        external_reference = node.external_reference_at(byte_offset)
        if external_reference is None:
            return None
        node = external_reference.referenced_declaration

    if not isinstance(node, VariableDeclaration):
        return None

    type_name = node.type_name
    if isinstance(type_name, UserDefinedTypeName):
        return [
            Location(
                uri=DocumentUri(path_to_uri(type_name.referenced_declaration.file)),
                range=context.compiler.get_range_from_byte_offsets(
                    type_name.referenced_declaration.file,
                    type_name.referenced_declaration.name_location,
                ),
            )
        ]
    else:
        return None
