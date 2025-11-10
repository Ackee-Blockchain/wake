from __future__ import annotations

import networkx as nx
import rich_click as click
import wake.ir as ir
import wake.ir.types as types
from rich import print
from wake.cli import SolidityName
from wake.printers import Printer, printer
#almost everything was foung at link below
#https://docs.soliditylang.org/en/v0.8.26/cheatsheet.html#abi-encoding-and-decoding-functions


"""
ABI.ENCODECALL: https://solidity-by-example.org/abi-encode/



"""



global_definitions = {
    "decode": "",
    
    "encode": "",
    
    "encodeCall": "", #ask Michal if function can be like this
    
    "encodePacked" : "",
    
    "encodeWithSelector" : "",
    
    "encodeWithSignature" : "",
        
    "addmod": "// compute: (x + y) % k, where k != 0\nfunction: addmod(uint x, uint y, uint k) returns (uint)",
    
    "balance": "// balance of the Address in Wei\nuint256 <address>.balance",
    
    "call":"<address>.call(bytes memory) returns (bool, bytes memory)",
    
    "code": "// code at the Address (can be empty)\nbytes memory <address>.code",
    
    "codehash": "// the codehash of the Address\nbytes32 <address>.codehash",
    
    "delegatecall": "<address>.delegatecall(bytes memory) returns (bool, bytes memory)",
    
    "send": "// send given amount of Wei to the Address\n<address_payable>.send(uint256 amount) returns (bool)",
    
    "staticcall": "<address>.staticcall(bytes memory) returns (bool, bytes memory)",
    
    "transfer": "// transfer given amount of Wei to the Address, throws on failure\n<address_payable>.transfer(uint256 amount)", #function??
    
    "length" : "// yields the fixed length of the byte array (read-only)",
    
    "pop" : "",
    
    "push" : "",
    
    "assert": "// ensure the condition is true, otherwise throw\nfunction assert(bool condition)",
    
    "blobhash": "// returns the hash of the blob at the given index associated with the current transaction\nfunction blobhash(uint index) returns (bytes32)",
    
    "blockhash": "// hash of the given block\nfunction blockhash(uint blockNumber) returns (bytes32)",
    
    "basefee": "// current block's base fee\nuint block.basefee",
    
    "blobbasefee": "// current block's blob base fee\nuint block.blobbasefee",
    
    "chainid": "// current chain id\nuint block.chainid",
    
    "coinbase": "// current block's miner address\naddress payable block.coinbase",
    
    "difficulty" : "// current block's difficulty\nuint block.difficulty",
    
    "gaslimit": "// current block's gas limit\nuint block.gaslimit",
    
    "number": "// current block number\nuint block.number",
    
    "prevrandao": "// random number provided by the beacon chain\nuint block.prevrandao",
    
    "timestamp": "// current block timestamp in seconds since Unix epoch\nuint block.timestamp",
    
    "concat": "// concatenate two byte/string arrays\nfunction bytes/string.concat(...) returns (bytes/string memory)",
    
    "ecrecover": "// recover the address associated with the public key from eliptic curve signature\necrecover(bytes32 hash, uint8 v, bytes32 r, bytes32 s) returns (address)",
    
    "address": "// returns the address", #TODO: is it ok?
    
    "gas": "", #TODO: idk what to write here
    
    "selector": "// returns the function selector", #TODO: is it ok?
    
    "value": "", #TODO: idk what to write here
    
    "gasleft": "// remaining gas\nuint256 gasleft()",
    
    "keccak256": "// compute the Keccak-256 hash of the input\nfunction keccak256(bytes memory) returns (bytes32)",
    
    "data": "// complete calldata\nbytes msg.data",
    
    "sender": "// Address of the sender of the message (current call)\nmsg.sender",
    
    "sig" : "// first four bytes of the calldata (i.e. function identifier)\nbytes4 msg.sig",
    
    "value": "// amount of Wei sent with the message\nuint msg.value",
    
    "mulmod": "// compute: (x * y) % k, where k != 0\nfunction mulmod(uint x, uint y, uint k) returns (uint)",
    
    "now" : "// current block timestamp (alias for block.timestamp)\nuint now", #TODO: check if it's ok
    
    "require": "", #done in code
    
    "revert": "// abort execution and revert state changes\nfunction revert(string memory message)",
    
    "ripemd160": "// compute the RIPEMD-160 hash of the input\nfunction ripemd160(bytes memory) returns (bytes20)",
    
    "selfdestruct": "// destroy the current contract, sending its funds to the recipient\nfunction selfdestruct(address payable recipient)",
    
    "sha256": "// compute the SHA-256 hash of the input\nfunction sha256(bytes memory) returns (bytes32)",
    
    "gasprice": "// gas price of the transaction\nuint tx.gasprice",
    
    "origin": "// sender of the transaction (full call chain)\naddress tx.origin",
    
    "creationCode": "// creation bytecode of the Contract\nbytes memory type(Contract).creationCode",
    
    "interfaceId": "// value containing the EIP-165 interface identifier of the given interface\nbytes4 type(Interface).interfaceId",
    
    "max": "", #done in code
    
    "min": "", #done in code
    
    "name": "// name of the contract\nstring memory type(Contract).name",
    
    "runtimeCode": "// runtime bytecode of the Contract\nbytes memory type(Contract).runtimeCode",
    
    "wrap": "", #TODO: cant find the right definition
    
    "unwrap": "", #TODO: cant find the right definition  

}



class LspGlobalSymbolsPrinterPrinter(Printer):
    execution_mode = "lsp"
    
    bit_sizes = [8, 16, 32, 64, 128, 256]
    signed_integers = [f"int{i}" for i in bit_sizes]   # ['int8', 'int16', 'int32', 'int64', 'int128', 'int256']
    unsigned_integers = [f"uint{i}" for i in bit_sizes] # ['uint8', 'uint16', 'uint32', 'uint64', 'uint128', 'uint256']
    
    
    
    
    def handle_abi_decode(self,parent_node: ir.MemberAccess):
        """
        unnecesary --> abi.decode is already checking for the types
        allowed_types = {
            "uint256", "int256", "uint128", "int128", "uint64", "int64",
            "uint32", "int32", "uint16", "int16", "uint8", "int8",
            "bool", "address", "bytes", "bytes32", "string"
        }
        """

        data = (parent_node.arguments[1].source).split(",") #assuming arguments[0] will always be encodedData --> rtn ['(address', ' uint256', ' bool)']
        cleaned_data = [item.replace('(', '').replace(')', '') for item in data] #get strings without brackets
        
        return f"```solidity\nfunction abi.decode(bytes memory encodedData, ({', '.join(cleaned_data)})) returns ({', '.join(cleaned_data)})\n```"
    
    
    def handle_abi_encode(self, parent_node: ir.MemberAccess):
        args = parent_node.arguments
        args_abi = [arg.type.abi_type for arg in args]
        
        return f"```solidity\nfunction abi.encode({', '.join(args_abi)}) returns (bytes memory)\n```"
    
    
    def handle_encode_call(self, parent_node: ir.MemberAccess):
        arg_1 = parent_node.arguments[0].source
        arg_2 = parent_node.arguments[1].type.abi_type
        
        return f"```solidity\nfunction abi.encodeCall({arg_1}, {arg_2}) returns (bytes memory)\n```"
    
    
    def handle_encode_packed(self, parent_node: ir.MemberAccess):
        args = parent_node.arguments
        args_abi = [arg.type_string for arg in args]
        
        
        return f"```solidity\nfunction abi.encodePacked({', '.join(args_abi)}) returns (bytes memory)\n```"
    
    def handle_encode_selector(self, parent_node: ir.MemberAccess):
        args = parent_node.arguments
        args_abi = [arg.type_string for arg in args]
        
        return f"```solidity\n// equivalent to:abi.encodeWithSignature(...)\nfunction abi.encodeWithSelector({', '.join(args_abi)}) returns (bytes memory)\n```"
    
    
    def handle_encode_signature(self, parent_node: ir.MemberAccess):
        args = parent_node.arguments
        args_abi = [arg.type_string for arg in args]
        
        return f"```solidity\n// equivalent to: abi.encodeWithSelector(...)\nfunction abi.encodeWithSignature({', '.join(args_abi)}) returns (bytes memory)\n```"
    
    
    def handle_push(self, parent_node: ir.MemberAccess):
        array_type = str(parent_node.expression.type_string).split("[")[0].replace("function", "")


        if len(parent_node.arguments) == 0:
            return f"```solidity\nfunction push() returns{array_type})\n```"
        else:
            array_type = array_type.replace(" ", "")
            return f"```solidity\nfunction push{array_type})\n```"
            
    
    """
    MemberAccess nodes: other symbols that are NOT in range between -1 to -99
    """
    def visit_member_access(self, node: ir.MemberAccess):
        hover_text = ""
        if node.member_name in global_definitions:
            parent = node.parent
            if node.type.abi_type in self.signed_integers or node.type.abi_type in self.unsigned_integers:
                hover_text = f"```solidity\n{node.type.abi_type} type({node.type.abi_type}).{node.member_name}\n```"
                
            elif node.member_name == "concat":
                args_0 = parent.arguments[0].type_string
                args_1 = parent.arguments[1].type_string

                if parent.type.abi_type == "bytes":
                    hover_text = f"```solidity\n// concatenate two byte arrays\nbytes.concat({args_0}, {args_1}) returns (bytes memory)\n```"
                else:
                    hover_text = f"```solidity\n// concatenate two string arrays\nstring.concat(string memory a, string memory b) returns (string memory)\n```"
                    
            elif node.member_name == "decode":
                assert isinstance(parent, ir.FunctionCall)
                hover_text = self.handle_abi_decode(parent)
                
            elif node.member_name == "encode":
                assert isinstance(parent, ir.FunctionCall)
                hover_text = self.handle_abi_encode(parent)
                
            elif node.member_name == "encodeCall":
                assert isinstance(parent, ir.FunctionCall)
                hover_text = self.handle_encode_call(parent)
            
            elif node.member_name == "encodePacked":
                assert isinstance(parent, ir.FunctionCall)
                hover_text = self.handle_encode_packed(parent)
                
            elif node.member_name == "encodeWithSelector":
                assert isinstance(parent, ir.FunctionCall)
                hover_text = self.handle_encode_selector(parent)
                
            elif node.member_name == "encodeWithSignature":
                # equivalent to: abi.encodeWithSelector
                assert isinstance(parent, ir.FunctionCall)
                hover_text = self.handle_encode_signature(parent)
                
            elif node.member_name == "push":
                assert isinstance(parent, ir.FunctionCall)
                hover_text = self.handle_push(parent)
                
            elif node.member_name == "pop":
                assert isinstance(parent, ir.FunctionCall)
                rtn = parent.expression.type_string.split("[")[0].replace("function", "")

                hover_text = f"```solidity\nfunction pop() returns{rtn})\n```"

            elif node.member_name == "wrap":
                assert isinstance(parent, ir.FunctionCall)
                arg = parent.arguments[0].type_string
                rtn = parent.parent.source.split(".")[0].split(" ")[1]
                hover_text = f"```solidity\nfunction wrap({arg}) returns ({rtn})\n```"

                

            elif node.member_name == "unwrap":
                assert isinstance(parent, ir.FunctionCall)
                rtn = parent.arguments[0].type_string
                abi_type = parent.arguments[0].type.abi_type
                
                hover_text = f"```solidity\nfunction unwrap({rtn}) returns ({abi_type})\n```"
                
            
            else:
                hover_text = f"```solidity\n{global_definitions[node.member_name]}\n```"
        
            assert self.lsp_provider is not None
            self.lsp_provider.add_hover(node, hover_text)
    


 
            
    """
    Identifier nodes: symbols of the Solidity language with identifiers between -1 to -99
    """        
    def visit_identifier(self, node: ir.Identifier):
        if node.name in global_definitions: 
            if node.name == "require":
                parent = node.parent
                assert isinstance(parent, ir.FunctionCall)
                if len(parent.arguments) == 1:
                    hover_text = f"```solidity\n// ensure the condition is true, otherwise throw\nrequire(bool condition) \n```"
                else:
                    hover_text = f"```solidity\n// ensure the condition is true, otherwise throw\nrequire(bool condition, string memory message)\n```"             
            elif node.name == "":
                pass
            
            else:
                hover_text = f"```solidity\n{global_definitions[node.name]}\n```" 
                
            
            
            
           
            
            assert self.lsp_provider is not None
            self.lsp_provider.add_hover(node, hover_text)
            
            
            
                
            
            
    
    def print(self) -> None:
        pass
    

    @printer.command(name="lsp_global_symbols_printer")
    def cli(self) -> None:
        pass
    
    
    






