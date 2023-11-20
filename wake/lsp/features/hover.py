import logging
from pathlib import Path
from typing import List, Optional, Tuple, Union

from wake.core import get_logger
from wake.ir import (
    BinaryOperation,
    ContractDefinition,
    DeclarationAbc,
    Identifier,
    IdentifierPath,
    IrAbc,
    MemberAccess,
    UnaryOperation,
    UserDefinedTypeName,
    YulIdentifier,
)

from ...core.solidity_version import SemanticVersion
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


yul_definitions = {
    "stop": "// stop execution, identical to return(0, 0)\nstop()",
    "add": "// x + y\nadd(x, y)",
    "sub": "// x - y\nsub(x, y)",
    "mul": "// x * y\nmul(x, y)",
    "div": "// x / y, 0 if y == 0\ndiv(x, y)",
    "sdiv": "// signed x / y, 0 if y == 0\nsdiv(x, y)",
    "mod": "// x % y, 0 if y == 0\nmod(x, y)",
    "smod": "// signed x % y, 0 if y == 0\nsmod(x, y)",
    "exp": "// x ** y\nexp(x, y)",
    "not": "// bitwise NOT\nnot(x)",
    "lt": "// 1 if x < y, 0 otherwise\nlt(x, y)",
    "gt": "// 1 if x > y, 0 otherwise\ngt(x, y)",
    "slt": "// 1 if signed x < signed y, 0 otherwise\nslt(x, y)",
    "sgt": "// 1 if signed x > signed y, 0 otherwise\nsgt(x, y)",
    "eq": "// 1 if x == y, 0 otherwise\neq(x, y)",
    "iszero": "// 1 if x == 0, 0 otherwise\niszero(x)",
    "and": "// bitwise AND\nand(x, y)",
    "or": "// bitwise OR\nor(x, y)",
    "xor": "// bitwise XOR\nxor(x, y)",
    "byte": "// retrieve the nth most significant byte of x\nbyte(n, x)",
    "shl": "// x << y\nshl(x, y)",
    "shr": "// x >> y\nshr(x, y)",
    "sar": "// signed x >> y\nsar(x, y)",
    "addmod": "// (x + y) % m, 0 if m == 0\naddmod(x, y, m)",
    "mulmod": "// (x * y) % m, 0 if m == 0\nmulmod(x, y, m)",
    "signextend": "// sign extend from (i * 8 + 7)th bit counting from least significant\nsignextend(i, x)",
    "keccak256": "// compute the Keccak-256 hash\nkeccak256(memStart, length)",
    "pc": "// current program counter\npc()",
    "pop": "// discard value returned by another instruction\npop(x)",
    "mload": "// load word from memory\nmload(memStart)",
    "mstore": "// store word to memory\nmstore(memStart, x)",
    "mstore8": "// store single byte to memory\nmstore8(memStart, x)",
    "sload": "// load word from storage\nsload(storageSlot)",
    "sstore": "// store word to storage\nsstore(storageSlot, x)",
    "msize": "// size of memory\nmsize()",
    "gas": "// remaining gas\ngas()",
    "address": "// address of the current contract / execution context\naddress()",
    "balance": "// wei balance of an address\nbalance(address)",
    "selfbalance": "// wei balance of the current contract / execution context, same as balance(address()) but cheaper\nselfbalance()",
    "caller": "// caller (excluding delegatecall), same as `msg.sender` in Solidity\ncaller()",
    "callvalue": "// wei sent with the call, same as `msg.value` in Solidity\ncallvalue()",
    "calldataload": "// load word from call data\ncalldataload(callDataStart)",
    "calldatasize": "// size of call data in bytes\ncalldatasize()",
    "calldatacopy": "// copy call data to memory\ncalldatacopy(memStart, callDataStart, length)",
    "codesize": "// size of code of the current contract / execution context\ncodesize()",
    "codecopy": "// copy code to memory\ncodecopy(memStart, codeStart, length)",
    "extcodesize": "// size of code at address\nextcodesize(address)",
    "extcodecopy": "// copy code at address to memory\nextcodecopy(address, memStart, codeStart, length)",
    "returndatasize": "// size of return data buffer\nreturndatasize()",
    "returndatacopy": "// copy return data to memory\nreturndatacopy(memStart, returnDataStart, length)",
    "extcodehash": "// Keccak-256 hash of code at address\nextcodehash(address)",
    "create": "// create contract with code from memory and value in wei, return new address or 0 on error\ncreate(value, memStart, length)",
    "create2": "// create contract from salt with code from memory and value in wei, return new address or 0 on error\ncreate2(value, memStart, length, salt)",
    "call": "// call contract at address providing gas, value in wei, call data from memory, storing return data to memory, return 1 on success or 0 on error\ncall(gas, address, value, memStartIn, memLengthIn, memStartOut, memLengthOut)",
    "callcode": "// call contract at address preserving execution context, providing gas, value in wei, call data from memory, storing return data to memory, return 1 on success or 0 on error\ncallcode(gas, address, value, memStartIn, memLengthIn, memStartOut, memLengthOut)",
    "delegatecall": "// call contract at address preserving execution context, current caller and call value, providing gas, call data from memory, storing return data to memory, return 1 on success or 0 on error\ndelegatecall(gas, address, memStartIn, memLengthIn, memStartOut, memLengthOut)",
    "staticcall": "// call contract at address disallowing state modifications, providing gas, call data from memory, storing return data to memory, return 1 on success or 0 on error\nstaticcall(gas, address, memStartIn, memLengthIn, memStartOut, memLengthOut)",
    "return": "// end execution, copy memory to return data buffer\nreturn(memStart, length)",
    "revert": "// end execution, revert state changes, copy memory to return data buffer\nrevert(memStart, length)",
    "selfdestruct": "// end execution, mark current contract to be destroyed, sending funds to address\nselfdestruct(address)",
    "invalid": "// end execution with invalid instruction, consume all remaining gas\ninvalid()",
    "log0": "// log without topics data from memory\nlog0(memStart, length)",
    "log1": "// log with one topic data from memory\nlog1(memStart, length, topic1)",
    "log2": "// log with two topics data from memory\nlog2(memStart, length, topic1, topic2)",
    "log3": "// log with three topics data from memory\nlog3(memStart, length, topic1, topic2, topic3)",
    "log4": "// log with four topics data from memory\nlog4(memStart, length, topic1, topic2, topic3, topic4)",
    "chainid": "// current chain ID\nchainid()",
    "basefee": "// current block's base fee\nbasefee()",
    "origin": "// sender of the transaction, same as `tx.origin` in Solidity\norigin()",
    "gasprice": "// gas price of the transaction, same as `tx.gasprice` in Solidity\ngasprice()",
    "blockhash": "// hash of the given block number, only for last 256 blocks excluding current\nblockhash(blockNumber)",
    "coinbase": "// current block's miner address\ncoinbase()",
    "timestamp": "// timestamp of the current block in seconds since the epoch\ntimestamp()",
    "number": "// current block number\nnumber()",
    "difficulty": "// current block's difficulty\ndifficulty()",
    "gaslimit": "// current block's gas limit\ngaslimit()",
    "prevrandao": "// previous block's RANDAO value\nprevrandao()",
}


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
        if (
            isinstance(node, ContractDefinition)
            and context.openzeppelin_contracts_version is not None
            and context.openzeppelin_contracts_version >= "2.0.0"
        ):
            value += _append_openzeppelin_docs(
                node, context.openzeppelin_contracts_version
            )

        return value, original_node_location
    elif isinstance(node, set):
        value = "\n".join(
            "```solidity\n"
            + node.declaration_string  # pyright: ignore reportGeneralTypeIssues
            + "\n```"
            for node in node
        )
        return value, original_node_location
    elif isinstance(node, YulIdentifier):
        if node.name in yul_definitions:
            return (
                f"```solidity\n{yul_definitions[node.name]}\n```",
                original_node_location,
            )
    return None


async def _get_hover_from_cache(path: Path, position: Position, context: LspContext):
    new_byte_offset = context.compiler.get_byte_offset_from_line_pos(
        path, position.line, position.character
    )
    backward_changes = context.compiler.get_last_compilation_backward_changes(path)
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

    if isinstance(node, DeclarationAbc):
        location = node.name_location
        forward_changes = context.compiler.get_last_compilation_forward_changes(path)
        if forward_changes is None:
            raise Exception("No forward changes found")
        new_start = (
            changes_to_byte_offset(forward_changes[0 : location[0]]) + location[0]
        )
        new_end = changes_to_byte_offset(forward_changes[0 : location[1]]) + location[1]
        node_name_location = (new_start, new_end)
    else:
        node_name_location = None

    result = _get_results_from_node(
        node, position, old_byte_offset, context, node_name_location
    )
    if result is None:
        return None

    value, location = result
    forward_changes = context.compiler.get_last_compilation_forward_changes(path)
    if forward_changes is None:
        raise Exception("No forward changes found")
    new_start = changes_to_byte_offset(forward_changes[0 : location[0]]) + location[0]
    new_end = changes_to_byte_offset(forward_changes[0 : location[1]]) + location[1]
    return Hover(
        contents=MarkupContent(
            kind=MarkupKind.MARKDOWN,
            value=value,
        ),
        range=context.compiler.get_range_from_byte_offsets(path, (new_start, new_end)),
    )


async def hover(context: LspContext, params: HoverParams) -> Optional[Hover]:
    logger.debug(
        f"Hover for file {params.text_document.uri} at position {params.position} requested"
    )

    path = uri_to_path(params.text_document.uri).resolve()
    if (
        path not in context.compiler.interval_trees
        or not context.compiler.output_ready.is_set()
    ):
        try:
            return await _get_hover_from_cache(path, params.position, context)
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
    logger.debug(f"Found {len(nodes)} nodes at position {params.position}")
    if len(nodes) == 0:
        return None

    node = max(nodes, key=lambda n: n.ast_tree_depth)

    if isinstance(node, DeclarationAbc):
        node_name_location = node.name_location
    else:
        node_name_location = None

    result = _get_results_from_node(
        node, params.position, byte_offset, context, node_name_location
    )
    if result is None:
        return None

    value, original_node_location = result
    return Hover(
        contents=MarkupContent(
            kind=MarkupKind.MARKDOWN,
            value=value,
        ),
        range=context.compiler.get_range_from_byte_offsets(
            path, original_node_location
        ),
    )
