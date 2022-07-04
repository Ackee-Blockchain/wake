import logging
from typing import Iterable, List, Union

from woke.ast.enums import GlobalSymbolsEnum
from woke.ast.ir.abc import IrAbc
from woke.ast.ir.declaration.abc import DeclarationAbc
from woke.ast.ir.declaration.function_definition import FunctionDefinition
from woke.ast.ir.declaration.modifier_definition import ModifierDefinition
from woke.ast.ir.declaration.variable_declaration import VariableDeclaration
from woke.ast.ir.expression.identifier import Identifier
from woke.ast.ir.expression.member_access import MemberAccess
from woke.ast.ir.meta.identifier_path import IdentifierPath
from woke.ast.ir.type_name.user_defined_type_name import UserDefinedTypeName
from woke.lsp.common_structures import (
    DocumentUri,
    Location,
    PartialResultParams,
    Position,
    Range,
    TextDocumentPositionParams,
    TextDocumentRegistrationOptions,
    WorkDoneProgressOptions,
    WorkDoneProgressParams,
)
from woke.lsp.context import LspContext
from woke.lsp.lsp_data_model import LspModel
from woke.lsp.utils.uri import path_to_uri, uri_to_path

logger = logging.getLogger(__name__)


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


def _generate_references(
    node_references: Iterable[
        Union[Identifier, IdentifierPath, MemberAccess, UserDefinedTypeName]
    ],
    context: LspContext,
) -> List[Location]:
    refs = []
    for reference in node_references:
        path = reference.file
        refs.append(
            Location(
                uri=DocumentUri(path_to_uri(path)),
                range=context.compiler.get_range_from_byte_offsets(
                    path, reference.byte_location
                ),
            )
        )
    return refs


def _generate_declaration_references(
    declaration: DeclarationAbc, include_declaration: bool, context: LspContext
) -> List[Location]:
    refs = []
    if include_declaration:
        path = declaration.file
        refs.append(
            Location(
                uri=DocumentUri(path_to_uri(path)),
                range=context.compiler.get_range_from_byte_offsets(
                    path, declaration.name_location
                ),
            )
        )

    refs.extend(_generate_references(declaration.references, context))
    return refs


async def references(
    context: LspContext, params: ReferenceParams
) -> Union[List[Location], None]:
    logger.debug(
        f"References for file {params.text_document.uri} at position {params.position} requested"
    )
    await context.compiler.output_ready.wait()

    refs = []
    path = uri_to_path(params.text_document.uri).resolve()

    if path in context.compiler.interval_trees:
        tree = context.compiler.interval_trees[path]

        byte_offset = context.compiler.get_byte_offset_from_line_pos(
            path, params.position.line, params.position.character
        )
        intervals = tree.at(byte_offset)
        nodes: List[IrAbc] = [interval.data for interval in intervals]
        logger.debug(f"Found {len(nodes)} nodes at byte offset {byte_offset}:\n{nodes}")

        node = max(nodes, key=lambda n: n.ast_tree_depth)
        logger.debug(f"Found node {node}")

        if isinstance(
            node, (Identifier, IdentifierPath, UserDefinedTypeName, MemberAccess)
        ):
            referenced_declaration = node.referenced_declaration
            if referenced_declaration is None:
                return None
            if isinstance(referenced_declaration, GlobalSymbolsEnum):
                global_refs = (
                    context.compiler.ir_reference_resolver.get_global_symbol_references(
                        referenced_declaration
                    )
                )
                if len(global_refs) > 0:
                    return _generate_references(global_refs, context)
                return None
            else:
                node = referenced_declaration

        if not isinstance(node, DeclarationAbc):
            return None

        processed_declarations = {node}
        declarations_queue: List[DeclarationAbc] = [node]

        while declarations_queue:
            declaration = declarations_queue.pop()
            refs.extend(
                _generate_declaration_references(
                    declaration, params.context.include_declaration, context
                )
            )

            if (
                isinstance(declaration, (FunctionDefinition, VariableDeclaration))
                and declaration.base_functions is not None
            ):
                for base_function in declaration.base_functions:
                    if base_function not in processed_declarations:
                        declarations_queue.append(base_function)
                        processed_declarations.add(base_function)
            if isinstance(declaration, FunctionDefinition):
                for child_function in declaration.child_functions:
                    if child_function not in processed_declarations:
                        declarations_queue.append(child_function)
                        processed_declarations.add(child_function)
            if isinstance(declaration, ModifierDefinition):
                if declaration.base_modifiers is not None:
                    for base_modifier in declaration.base_modifiers:
                        if base_modifier not in processed_declarations:
                            declarations_queue.append(base_modifier)
                            processed_declarations.add(base_modifier)
                for child_modifier in declaration.child_modifiers:
                    if child_modifier not in processed_declarations:
                        declarations_queue.append(child_modifier)
                        processed_declarations.add(child_modifier)

    if len(refs) == 0:
        return None
    return refs
