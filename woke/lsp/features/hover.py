import logging
from typing import List, Optional, Tuple, Union

import woke.ast.ir.yul as yul

from ...ast.ir.abc import IrAbc
from ...ast.ir.declaration.abc import DeclarationAbc
from ...ast.ir.declaration.contract_definition import ContractDefinition
from ...ast.ir.expression.identifier import Identifier
from ...ast.ir.expression.member_access import MemberAccess
from ...ast.ir.meta.identifier_path import IdentifierPath
from ...ast.ir.type_name.user_defined_type_name import UserDefinedTypeName
from ...core.solidity_version import SemanticVersion
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


def _append_openzeppelin_docs(
    node: ContractDefinition, version: SemanticVersion
) -> str:
    source_unit = node.parent
    version_string = f"{version.major}.x"
    url_base = f"https://docs.openzeppelin.com/contracts/{version_string}"
    doc_url = None
    api_doc_url = None

    if "openzeppelin/contracts/access" in source_unit.source_unit_name:
        doc_url = "access-control"
        api_doc_url = "access"
    elif "openzeppelin/contracts/crosschain" in source_unit.source_unit_name:
        doc_url = "crosschain"
        api_doc_url = "crosschain"
    elif "openzeppelin/contracts/finance" in source_unit.source_unit_name:
        if node.name == "PaymentSplitter":
            doc_url = "utilities#payment"
        api_doc_url = "finance"
    elif "openzeppelin/contracts/governance" in source_unit.source_unit_name:
        doc_url = "governance"
        api_doc_url = "governance"
    elif (
        "openzeppelin/contracts/interfaces" in source_unit.source_unit_name
        or "openzeppelin/contracts/token" in source_unit.source_unit_name
    ):
        if "ERC20" in node.name:
            doc_url = "erc20"
            api_doc_url = "token/erc20"
        elif "ERC721" in node.name:
            doc_url = "erc721"
            api_doc_url = "token/erc721"
        elif "ERC777" in node.name:
            doc_url = "erc777"
            api_doc_url = "token/erc777"
        elif "ERC1155" in node.name:
            doc_url = "erc1155"
            api_doc_url = "token/erc1155"
        elif node.name.startswith("I"):
            api_doc_url = "interfaces"
        else:
            api_doc_url = "token/common"
    elif "openzeppelin/contracts/metatx" in source_unit.source_unit_name:
        api_doc_url = "metatx"
    elif "openzeppelin/contracts/proxy" in source_unit.source_unit_name:
        api_doc_url = "proxy"
    elif "openzeppelin/contracts/security" in source_unit.source_unit_name:
        if node.name == "PullPayment":
            doc_url = "utilities#payment"
        api_doc_url = "security"
    elif "openzeppelin/contracts/utils" in source_unit.source_unit_name:
        doc_url = "utilities"
        api_doc_url = "utils"
    elif "openzeppelin/contracts/GSN" in source_unit.source_unit_name:
        doc_url = "gsn"
        api_doc_url = "gsn"
    elif "openzeppelin/contracts/cryptography" in source_unit.source_unit_name:
        doc_url = "utilities#cryptography"
        api_doc_url = "cryptography"
    elif "openzeppelin/contracts/drafts" in source_unit.source_unit_name:
        api_doc_url = "drafts"
    elif "openzeppelin/contracts/math" in source_unit.source_unit_name:
        doc_url = "utilities#math"
        api_doc_url = "math"
    elif "openzeppelin/contracts/payment" in source_unit.source_unit_name:
        doc_url = "utilities#payment"
        api_doc_url = "payment"
    elif "openzeppelin/contracts/presets" in source_unit.source_unit_name:
        if "ERC20" in node.name:
            doc_url = "erc20#Presets"
        elif "ERC721" in node.name:
            doc_url = "erc721#Presets"
        elif "ERC777" in node.name:
            doc_url = "erc777#Presets"
        elif "ERC1155" in node.name:
            doc_url = "erc1155#Presets"
        api_doc_url = "presets"

    ret = ""
    if doc_url is not None:
        ret += f"\n\n[OpenZeppelin documentation]({url_base}/{doc_url})"
    if api_doc_url is not None:
        ret += f"\n\n[OpenZeppelin API documentation]({url_base}/api/{api_doc_url}#{node.name})"
    return ret


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
    elif isinstance(node, yul.Identifier):
        external_reference = node.external_reference
        if external_reference is None:
            return None
        node = external_reference.referenced_declaration
        original_node_location = external_reference.byte_location

    if not isinstance(node, DeclarationAbc):
        return None

    value = "```solidity\n" + node.declaration_string + "\n```"
    if (
        isinstance(node, ContractDefinition)
        and context.openzeppelin_contracts_version is not None
        and context.openzeppelin_contracts_version >= "2.0.0"
    ):
        value += _append_openzeppelin_docs(node, context.openzeppelin_contracts_version)

    return Hover(
        contents=MarkupContent(
            kind=MarkupKind.MARKDOWN,
            value=value,
        ),
        range=context.compiler.get_range_from_byte_offsets(
            path, original_node_location
        ),
    )
