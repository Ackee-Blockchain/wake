import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Union

from wake.core import get_logger
from wake.ir import (
    BinaryOperation,
    ContractDefinition,
    DeclarationAbc,
    FunctionDefinition,
    Identifier,
    IdentifierPath,
    InheritanceSpecifier,
    IrAbc,
    MemberAccess,
    ModifierDefinition,
    ModifierInvocation,
    NewExpression,
    SourceUnit,
    UnaryOperation,
    UserDefinedTypeName,
    VariableDeclaration,
    YulIdentifier,
)
from wake.ir.enums import FunctionKind, GlobalSymbol
from wake.lsp.common_structures import (
    DocumentUri,
    Location,
    LocationLink,
    PartialResultParams,
    Position,
    TextDocumentPositionParams,
    TextDocumentRegistrationOptions,
    WorkDoneProgressOptions,
    WorkDoneProgressParams,
)
from wake.lsp.context import LspContext
from wake.lsp.lsp_compiler import LspCompiler
from wake.lsp.utils import path_to_uri, position_within_range, uri_to_path
from wake.lsp.utils.position import changes_to_byte_offset

logger = get_logger(__name__)


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


def _get_results_from_node(
    original_node: Union[IrAbc, GlobalSymbol],
    position: Position,
    context: LspContext,
    byte_offset: int,
    node_name_location: Optional[Tuple[int, int]],
) -> Optional[List[Tuple[Path, Tuple[int, int]]]]:
    def resolve(node) -> Set[Tuple[Path, Tuple[int, int]]]:
        ret = set()
        if isinstance(node, (FunctionDefinition, VariableDeclaration)):
            if isinstance(node, VariableDeclaration) or node.implemented:
                ret.add((node.source_unit.file, node.name_location))

            for base_function in node.base_functions:
                if base_function.implemented:
                    ret.add(
                        (base_function.source_unit.file, base_function.name_location)
                    )
            if isinstance(node, FunctionDefinition):
                for child_function in node.child_functions:
                    if isinstance(child_function, VariableDeclaration):
                        ret.add(
                            (
                                child_function.source_unit.file,
                                child_function.name_location,
                            )
                        )
                    elif (
                        isinstance(child_function, FunctionDefinition)
                        and child_function.implemented
                    ):
                        ret.add(
                            (
                                child_function.source_unit.file,
                                child_function.name_location,
                            )
                        )
        elif isinstance(node, ModifierDefinition):
            if node.implemented:
                ret.add((node.source_unit.file, node.name_location))
            for base_modifier in node.base_modifiers:
                if base_modifier.implemented:
                    ret.add(
                        (base_modifier.source_unit.file, base_modifier.name_location)
                    )
            for child_modifier in node.child_modifiers:
                if child_modifier.implemented:
                    ret.add(
                        (child_modifier.source_unit.file, child_modifier.name_location)
                    )
        elif isinstance(node, SourceUnit):
            ret.add((node.file, node.byte_location))
        else:
            ret.add((node.source_unit.file, node.name_location))

        return ret

    if isinstance(original_node, DeclarationAbc):
        assert node_name_location is not None
        name_location_range = context.compiler.get_range_from_byte_offsets(
            original_node.source_unit.file, node_name_location
        )
        if position_within_range(position, name_location_range):
            return [(original_node.source_unit.file, original_node.name_location)]
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
    elif (
        isinstance(original_node, (UnaryOperation, BinaryOperation))
        and original_node.function is not None
    ):
        node = original_node.function
    else:
        node = original_node

    if not isinstance(node, (DeclarationAbc, SourceUnit, set)):
        return None

    if isinstance(node, set):
        definitions = set()
        for n in node:
            definitions |= resolve(n)
    elif isinstance(node, ContractDefinition):
        assert not isinstance(original_node, GlobalSymbol)
        n = original_node
        if isinstance(n, IdentifierPath) and isinstance(n.parent, UserDefinedTypeName):
            n = n.parent
        if isinstance(n.parent, (ModifierInvocation, NewExpression)) or (
            isinstance(n.parent, InheritanceSpecifier)
            and n.parent.arguments is not None
        ):
            try:
                constructor = next(
                    f for f in node.functions if f.kind == FunctionKind.CONSTRUCTOR
                )
                definitions = resolve(constructor)
            except StopIteration:
                definitions = resolve(node)
        else:
            definitions = resolve(node)
    else:
        definitions = resolve(node)

    return list(definitions)


def _get_definition_from_cache(
    path: Path,
    position: Position,
    context: LspContext,
):
    new_byte_offset = context.compiler.get_early_byte_offset_from_line_pos(
        path, position.line, position.character
    )
    backward_changes = context.compiler.get_last_compilation_backward_changes(
        path, path
    )
    if backward_changes is None:
        raise Exception("No backward changes found")
    changes_before = backward_changes[0:new_byte_offset]
    old_byte_offset = changes_to_byte_offset(changes_before) + new_byte_offset

    tree = context.compiler.last_compilation_interval_trees[path]

    intervals = tree.at(old_byte_offset)
    nodes: List[IrAbc] = [interval.data for interval in intervals]
    if len(nodes) == 0:
        raise ValueError(f"Could not find node at {old_byte_offset}")

    node = max(nodes, key=lambda n: n.ast_tree_depth)

    if isinstance(node, (IdentifierPath, UserDefinedTypeName)):
        node = node.identifier_path_part_at(old_byte_offset)

    try:
        result: Dict[
            Path, Set[Tuple[int, int]]
        ] = context.compiler.go_to_definition_cache[
            node  # pyright: ignore reportArgumentType
        ]
    except KeyError:
        return None

    ret = []
    for location_path in result.keys():
        if not result[location_path]:
            continue

        forward_changes = context.compiler.get_last_compilation_forward_changes(
            path, location_path
        )
        if forward_changes is None:
            raise Exception("No forward changes found")

        for location in result[location_path]:
            # make sure the location was not removed
            if len(forward_changes[location[0] : location[1]]) > 0:
                continue

            new_start = (
                changes_to_byte_offset(forward_changes[0 : location[0]]) + location[0]
            )
            new_end = (
                changes_to_byte_offset(forward_changes[0 : location[1]]) + location[1]
            )

            ret.append(
                Location(
                    uri=DocumentUri(path_to_uri(location_path)),
                    range=context.compiler.get_early_range_from_byte_offsets(
                        location_path, (new_start, new_end)
                    ),
                )
            )

    if len(ret) == 0:
        return None
    elif len(ret) == 1:
        return ret[0]
    else:
        return ret


async def definition(
    context: LspContext, params: DefinitionParams
) -> Union[Location, List[Location], List[LocationLink], None]:
    logger.debug(
        f"Requested definition for file {params.text_document.uri} at {params.position}"
    )

    path = uri_to_path(params.text_document.uri).resolve()

    await next(
        asyncio.as_completed(
            [
                context.compiler.compilation_ready.wait(),
                context.compiler.cache_ready.wait(),
            ]
        )
    )

    if (
        path not in context.compiler.interval_trees
        or not context.compiler.compilation_ready.is_set()
    ):
        # try to use old build artifacts
        try:
            await context.compiler.cache_ready.wait()
            return _get_definition_from_cache(path, params.position, context)
        except Exception:
            pass

    await context.compiler.compilation_ready.wait()
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
        return _create_location(path, location, context.compiler)
    else:
        return [
            _create_location(path, location, context.compiler)
            for path, location in result
        ]
