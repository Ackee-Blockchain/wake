import asyncio
import logging
from pathlib import Path
from typing import List, Optional, Tuple, Union

from wake.core import get_logger
from wake.ir import (
    BinaryOperation,
    DeclarationAbc,
    Identifier,
    IdentifierPath,
    IrAbc,
    MemberAccess,
    UnaryOperation,
    UserDefinedTypeName,
    YulIdentifier,
)

from ..common_structures import (
    MarkupContent,
    MarkupKind,
    Position,
    Range,
    TextDocumentPositionParams,
    TextDocumentRegistrationOptions,
    WorkDoneProgressOptions,
    WorkDoneProgressParams,
)
from ..context import LspContext
from ..lsp_data_model import LspModel
from ..utils import position_within_range, uri_to_path
from ..utils.position import changes_to_byte_offset

logger = get_logger(__name__)


class HoverClientCapabilities(LspModel):
    dynamic_registration: Optional[bool] = None
    content_format: Optional[List[MarkupKind]] = None


class HoverOptions(WorkDoneProgressOptions):
    pass


class HoverRegistrationOptions(TextDocumentRegistrationOptions, HoverOptions):
    pass


class HoverParams(TextDocumentPositionParams, WorkDoneProgressParams):
    pass


class MarkedString(LspModel):
    language: str
    value: str


MarkedStringType = Union[str, MarkedString]


class Hover(LspModel):
    contents: Union[MarkedStringType, List[MarkedStringType], MarkupContent]
    range: Optional[Range] = None


def _get_results_from_node(
    original_node: IrAbc,
    position: Position,
    byte_offset: int,
    context: LspContext,
    node_name_location: Optional[Tuple[int, int]],
) -> Optional[Tuple[str, Tuple[int, int]]]:
    original_node_location: Tuple[int, int] = original_node.byte_location
    logger.debug(f"Found node {original_node}")

    if isinstance(original_node, DeclarationAbc):
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
        original_node_location = part.byte_location
    elif isinstance(original_node, YulIdentifier):
        external_reference = original_node.external_reference
        if external_reference is not None:
            node = external_reference.referenced_declaration
            original_node_location = external_reference.byte_location
        else:
            node = original_node
    elif (
        isinstance(original_node, (UnaryOperation, BinaryOperation))
        and original_node.function is not None
    ):
        node = original_node.function
    else:
        node = original_node

    if isinstance(node, DeclarationAbc):
        value = "```solidity\n" + node.declaration_string + "\n```"
        return value, original_node_location
    elif isinstance(node, set):
        value = "\n".join(
            "```solidity\n"
            + node.declaration_string  # pyright: ignore reportGeneralTypeIssues
            + "\n```"
            for node in node
        )
        return value, original_node_location
    return None


def _get_hover_from_cache(path: Path, position: Position, context: LspContext):
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
        if node is None:
            return None

    results = []
    if isinstance(node, DeclarationAbc):
        if node.name_location[0] <= old_byte_offset < node.name_location[1]:
            results.append(f"```solidity\n{node.declaration_string}\n```")
    else:
        try:
            results.append(context.compiler.hover_cache[node])
        except KeyError:
            pass

    forward_changes = context.compiler.get_last_compilation_forward_changes(path, path)
    if forward_changes is not None:
        new_node_start = changes_to_byte_offset(forward_changes[0 : node.byte_location[0]]) + node.byte_location[0]
        new_node_end = changes_to_byte_offset(forward_changes[0 : node.byte_location[1]]) + node.byte_location[1]

        results.extend(_get_hover_from_printers(context, path, new_byte_offset, (new_node_start, new_node_end)))
        results.extend(_get_hover_from_detectors(context, path, new_byte_offset, (new_node_start, new_node_end)))

    if len(results) == 0:
        return None

    forward_changes = context.compiler.get_last_compilation_forward_changes(path, path)
    if forward_changes is None:
        raise Exception("No forward changes found")
    new_start = changes_to_byte_offset(forward_changes[0 : node.byte_location[0]]) + node.byte_location[0]
    new_end = changes_to_byte_offset(forward_changes[0 : node.byte_location[1]]) + node.byte_location[1]
    return Hover(
        contents=MarkupContent(
            kind=MarkupKind.MARKDOWN,
            value="\n***\n".join(results),
        ),
        range=context.compiler.get_early_range_from_byte_offsets(path, (new_start, new_end)),
    )


def _get_hover_from_printers(context: LspContext, path: Path, byte_offset: int, node_offsets: Tuple[int, int]) -> List[str]:
    backward_changes = context.compiler.get_printer_backward_changes(path)
    if backward_changes is None or len(backward_changes[node_offsets[0]:node_offsets[1]]) > 0:
        return []

    old_byte_offset = changes_to_byte_offset(backward_changes[0:byte_offset]) + byte_offset
    old_node_start = changes_to_byte_offset(backward_changes[0:node_offsets[0]]) + node_offsets[0]
    old_node_end = changes_to_byte_offset(backward_changes[0:node_offsets[1]]) + node_offsets[1]

    return [
        o.text
        for o in context.compiler.get_printer_hovers(path, old_byte_offset, (old_node_start, old_node_end))
    ]


def _get_hover_from_detectors(context: LspContext, path: Path, byte_offset: int, node_offsets: Tuple[int, int]) -> List[str]:
    backward_changes = context.compiler.get_detector_backward_changes(path)
    if backward_changes is None or len(backward_changes[node_offsets[0]:node_offsets[1]]) > 0:
        return []

    old_byte_offset = changes_to_byte_offset(backward_changes[0:byte_offset]) + byte_offset
    old_node_start = changes_to_byte_offset(backward_changes[0:node_offsets[0]]) + node_offsets[0]
    old_node_end = changes_to_byte_offset(backward_changes[0:node_offsets[1]]) + node_offsets[1]

    return [
        o.text
        for o in context.compiler.get_detector_hovers(path, old_byte_offset, (old_node_start, old_node_end))
    ]


async def hover(context: LspContext, params: HoverParams) -> Optional[Hover]:
    logger.debug(
        f"Hover for file {params.text_document.uri} at position {params.position} requested"
    )

    path = uri_to_path(params.text_document.uri).resolve()

    await next(asyncio.as_completed(
        [context.compiler.compilation_ready.wait(), context.compiler.cache_ready.wait()]
    ))

    if (
        path not in context.compiler.interval_trees
        or not context.compiler.compilation_ready.is_set()
    ):
        try:
            await context.compiler.cache_ready.wait()
            return _get_hover_from_cache(path, params.position, context)
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
    logger.debug(f"Found {len(nodes)} nodes at position {params.position}")
    if len(nodes) == 0:
        return None

    node = max(nodes, key=lambda n: n.ast_tree_depth)

    if isinstance(node, DeclarationAbc):
        node_name_location = node.name_location
    else:
        node_name_location = None

    results = []
    definition_result = _get_results_from_node(
        node, params.position, byte_offset, context, node_name_location
    )
    if definition_result is not None:
        results.append(definition_result[0])

    results.extend(_get_hover_from_printers(context, path, byte_offset, node.byte_location))
    results.extend(_get_hover_from_detectors(context, path, byte_offset, node.byte_location))

    return Hover(
        contents=MarkupContent(
            kind=MarkupKind.MARKDOWN,
            value="\n***\n".join(results),
        ),
        range=context.compiler.get_range_from_byte_offsets(path, node.byte_location),
    )
