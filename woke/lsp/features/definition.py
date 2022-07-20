import logging
from pathlib import Path
from typing import List, Tuple, Union

from woke.ast.ir.abc import IrAbc
from woke.ast.ir.declaration.abc import DeclarationAbc
from woke.ast.ir.declaration.function_definition import FunctionDefinition
from woke.ast.ir.declaration.modifier_definition import ModifierDefinition
from woke.ast.ir.declaration.variable_declaration import VariableDeclaration
from woke.ast.ir.expression.identifier import Identifier
from woke.ast.ir.expression.member_access import MemberAccess
from woke.ast.ir.meta.identifier_path import IdentifierPath, IdentifierPathPart
from woke.ast.ir.statement.inline_assembly import InlineAssembly
from woke.ast.ir.type_name.user_defined_type_name import UserDefinedTypeName
from woke.lsp.common_structures import (
    DocumentUri,
    Location,
    LocationLink,
    PartialResultParams,
    TextDocumentPositionParams,
    TextDocumentRegistrationOptions,
    WorkDoneProgressOptions,
    WorkDoneProgressParams,
)
from woke.lsp.context import LspContext
from woke.lsp.lsp_compiler import LspCompiler
from woke.lsp.utils import path_to_uri, position_within_range, uri_to_path

logger = logging.getLogger(__name__)


class DefinitionOptions(WorkDoneProgressOptions):
    pass


class DefinitionRegistrationOptions(TextDocumentRegistrationOptions, DefinitionOptions):
    pass


class DefinitionParams(
    TextDocumentPositionParams, WorkDoneProgressParams, PartialResultParams
):
    pass


def _create_location(
    path: Path, location: Tuple[int, int], compiler: LspCompiler
) -> Location:
    return Location(
        uri=DocumentUri(path_to_uri(path)),
        range=compiler.get_range_from_byte_offsets(path, location),
    )


async def definition(
    context: LspContext, params: DefinitionParams
) -> Union[Location, List[Location], List[LocationLink], None]:
    logger.debug(
        f"Requested definition for file {params.text_document.uri} at {params.position}"
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
            node.file, node.name_location
        )
        if position_within_range(params.position, name_location_range):
            return _create_location(node.file, node.name_location, context.compiler)
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

    if not isinstance(node, DeclarationAbc):
        return None

    definitions: List[Location] = []

    if isinstance(node, (FunctionDefinition, VariableDeclaration)):
        if isinstance(node, VariableDeclaration) or node.implemented:
            definitions.append(
                _create_location(node.file, node.name_location, context.compiler)
            )

        if node.base_functions is not None:
            for base_function in node.base_functions:
                if base_function.implemented:
                    definitions.append(
                        _create_location(
                            base_function.file,
                            base_function.name_location,
                            context.compiler,
                        )
                    )
        if isinstance(node, FunctionDefinition):
            for child_function in node.child_functions:
                if isinstance(child_function, VariableDeclaration):
                    definitions.append(
                        _create_location(
                            child_function.file,
                            child_function.name_location,
                            context.compiler,
                        )
                    )
                elif (
                    isinstance(child_function, FunctionDefinition)
                    and child_function.implemented
                ):
                    definitions.append(
                        _create_location(
                            child_function.file,
                            child_function.name_location,
                            context.compiler,
                        )
                    )
    elif isinstance(node, ModifierDefinition):
        if node.implemented:
            definitions.append(
                _create_location(node.file, node.name_location, context.compiler)
            )
        if node.base_modifiers is not None:
            for base_modifier in node.base_modifiers:
                if base_modifier.implemented:
                    definitions.append(
                        _create_location(
                            base_modifier.file,
                            base_modifier.name_location,
                            context.compiler,
                        )
                    )
        for child_modifier in node.child_modifiers:
            if child_modifier.implemented:
                definitions.append(
                    _create_location(
                        child_modifier.file,
                        child_modifier.name_location,
                        context.compiler,
                    )
                )
    else:
        definitions.append(
            _create_location(node.file, node.name_location, context.compiler)
        )

    return definitions
