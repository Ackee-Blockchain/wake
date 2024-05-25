from __future__ import annotations

import networkx as nx
import rich_click as click
from rich import print

import wake.ir as ir
import wake.ir.types as types
from wake.cli import SolidityName
from wake.printers import Printer, printer

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
    "tload": "// load word from transient storage\ntload(transientSlot)",
    "tstore": "// store word to transient storage\ntstore(transientSlot, x)",
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
    "mcopy": "// copy memory to memory\nmcopy(memStartFrom, memStartTo, length)",
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
    "blobbasefee": "// current block's blob base fee\nblobbasefee()",
    "origin": "// sender of the transaction, same as `tx.origin` in Solidity\norigin()",
    "gasprice": "// gas price of the transaction, same as `tx.gasprice` in Solidity\ngasprice()",
    "blockhash": "// hash of the given block number, only for last 256 blocks excluding current\nblockhash(blockNumber)",
    "blobhash": "// versioned hash of transaction's i-th blob\nblobhash(i)",
    "coinbase": "// current block's miner address\ncoinbase()",
    "timestamp": "// timestamp of the current block in seconds since the epoch\ntimestamp()",
    "number": "// current block number\nnumber()",
    "difficulty": "// current block's difficulty\ndifficulty()",
    "gaslimit": "// current block's gas limit\ngaslimit()",
    "prevrandao": "// previous block's RANDAO value\nprevrandao()",
}


class LspYulDefinitionsPrinter(Printer):
    execution_mode = "lsp"

    def print(self) -> None:
        pass

    def visit_yul_identifier(self, node: ir.YulIdentifier):
        if node.name in yul_definitions:
            hover_text = f"```solidity\n{yul_definitions[node.name]}\n```"

            assert self.lsp_provider is not None
            self.lsp_provider.add_hover(node, hover_text)

    @printer.command(name="lsp-yul-definitions")
    def cli(self) -> None:
        pass
