import logging
from typing import List, Optional, Tuple, Union

from ...ast.ir.abc import IrAbc
from ...ast.ir.declaration.abc import DeclarationAbc
from ...ast.ir.expression.identifier import Identifier
from ...ast.ir.expression.member_access import MemberAccess
from ...ast.ir.meta.identifier_path import IdentifierPath
from ...ast.ir.statement.inline_assembly import InlineAssembly
from ...ast.ir.type_name.user_defined_type_name import UserDefinedTypeName
from ..common_structures import (
    MarkupContent,
    MarkupKind,
    Range,
    TextDocumentPositionParams,
    TextDocumentRegistrationOptions,
    WorkDoneProgressOptions,
    WorkDoneProgressParams,
)
from ..context import LspContext
from ..lsp_data_model import LspModel
from ..utils import position_within_range, uri_to_path

logger = logging.getLogger(__name__)


class HoverClientCapabilities(LspModel):
    dynamic_registration: Optional[bool]
    content_format: Optional[List[MarkupKind]]


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
    range: Optional[Range]


async def hover(context: LspContext, params: HoverParams) -> Optional[Hover]:
    logger.debug(
        f"Hover for file {params.text_document.uri} at position {params.position} requested"
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
    logger.debug(f"Found {len(nodes)} nodes at position {params.position}")
    if len(nodes) == 0:
        return None

    node = max(nodes, key=lambda n: n.ast_tree_depth)
    original_node_location: Tuple[int, int] = node.byte_location
    logger.debug(f"Found node {node}")

    if isinstance(node, DeclarationAbc):
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
        original_node_location = part.byte_location
    elif isinstance(node, InlineAssembly):
        external_reference = node.external_reference_at(byte_offset)
        if external_reference is None:
            return None
        node = external_reference.referenced_declaration
        original_node_location = external_reference.byte_location

    if not isinstance(node, DeclarationAbc):
        return None

    return Hover(
        contents=MarkupContent(
            kind=MarkupKind.MARKDOWN,
            value="```solidity\n" + node.declaration_string + "\n```",
        ),
        range=context.compiler.get_range_from_byte_offsets(
            path, original_node_location
        ),
    )
