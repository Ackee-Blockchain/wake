import logging
from typing import List, Union

from woke.ast.ir.abc import IrAbc
from woke.ast.ir.declaration.function_definition import FunctionDefinition
from woke.ast.ir.declaration.modifier_definition import ModifierDefinition
from woke.ast.ir.declaration.variable_declaration import VariableDeclaration
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
from woke.lsp.utils import path_to_uri, uri_to_path

logger = logging.getLogger(__name__)


class ImplementationOptions(WorkDoneProgressOptions):
    pass


class ImplementationRegistrationOptions(
    TextDocumentRegistrationOptions, ImplementationOptions, StaticRegistrationOptions
):
    pass


class ImplementationParams(
    TextDocumentPositionParams, WorkDoneProgressParams, PartialResultParams
):
    pass


async def implementation(
    context: LspContext, params: ImplementationParams
) -> Union[Location, List[Location], List[LocationLink], None]:
    logger.debug(
        f"Go to implementation for file {params.text_document.uri} at position {params.position} requested"
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

    if not isinstance(node, (FunctionDefinition, ModifierDefinition)):
        return None

    if node.implemented:
        return None

    implementations = []
    if isinstance(node, FunctionDefinition):
        for child_function in node.child_functions:
            if isinstance(child_function, FunctionDefinition):
                if child_function.implemented:
                    implementations.append(
                        Location(
                            uri=DocumentUri(path_to_uri(child_function.file)),
                            range=context.compiler.get_range_from_byte_offsets(
                                child_function.file, child_function.name_location
                            ),
                        )
                    )
            elif isinstance(child_function, VariableDeclaration):
                implementations.append(
                    Location(
                        uri=DocumentUri(path_to_uri(child_function.file)),
                        range=context.compiler.get_range_from_byte_offsets(
                            child_function.file, child_function.name_location
                        ),
                    )
                )
    elif isinstance(node, ModifierDefinition):
        for child_modifier in node.child_modifiers:
            if child_modifier.implemented:
                implementations.append(
                    Location(
                        uri=DocumentUri(path_to_uri(child_modifier.file)),
                        range=context.compiler.get_range_from_byte_offsets(
                            child_modifier.file, child_modifier.name_location
                        ),
                    )
                )

    if len(implementations) == 0:
        return None
    return implementations
