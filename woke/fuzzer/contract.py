from multiprocessing.sharedctypes import Value
from typing import Any, Iterable, Optional, Type, overload
from enum import IntEnum

import eth_abi
import web3.contract
from eth_typing import HexStr, AnyAddress
from web3 import Web3
from web3._utils.abi import get_abi_output_types
from web3._utils.compat import TypedDict
from web3.types import TxParams, RPCEndpoint
from web3.method import Method

from woke.fuzzer.abi_to_type import RequestType

import time

from woke.fuzzer.development_chains import DevChainABC, AnvilDevChain, HardhatDevChain

class NetworkKind(IntEnum):
    ANVIL = 0,
    HARDHAT = 1,
    GANACHE = 2,
    GETH = 3


class Abi:
    @classmethod
    def encode(self, arguments: Iterable, types: Iterable) -> HexStr:
        return eth_abi.encode(types, arguments)

    @classmethod
    def decode(self, data: bytes, types: Iterable) -> Any:
        return eth_abi.decode(types, data)


#global interface for communicating with the devchain
class DevchainInterface:
    #__network: NetworkKind
    __dev_chain: DevChainABC
    __port: int
    __w3: Web3

    def __init__(self, port: int):
        self.__port = port
        self.__w3 = Web3(Web3.WebsocketProvider(f"ws://127.0.0.1:{str(port)}", websocket_timeout=60))
        #self.__w3 = Web3(Web3.IPCProvider(f"/tmp/anvil.ipc"))
        #self.__w3 = Web3(Web3.HTTPProvider(f"http://127.0.0.1:{str(port)}"))
        self.__w3.eth.attach_methods({
            "trace_transaction": Method(RPCEndpoint("trace_transaction")),
            # TODO call
            "debug_trace_transaction": Method(RPCEndpoint("debug_traceTransaction")),
            "anvil_enable_traces": Method(RPCEndpoint("anvil_enableTraces")),  # currently not implemented in anvil - ValueError: {'code': -32603, 'message': 'Not implemented'}
        })
        self.__w3.eth.default_account = self.__w3.eth.accounts[0]
        print(f"default acc: {self.__w3.eth.default_account}")
        client_version: str = self.__w3.clientVersion.lower()
        print(f"client version: {client_version}")
        if "anvil" in client_version:
            self.__dev_chain = AnvilDevChain(self.__w3)
        elif "hardhat" in client_version:
            self.__dev_chain = HardhatDevChain(self.__w3)
        #elif "ethereumjs" in client_version:
        #    self.__network = NetworkKind.GANACHE
        #else:
        #    self.__network = NetworkKind.GETH
        

    @property
    def dev_chain(self):
        return self.__dev_chain
    

    def deploy(self, abi, bytecode, arguments: Iterable, params: Optional[TxParams] = None) -> web3.contract.Contract:
        factory = self.__w3.eth.contract(abi=abi, bytecode=bytecode)
        tx_hash = factory.constructor(*arguments).transact(params)
        tx_receipt = self.__w3.eth.wait_for_transaction_receipt(tx_hash)
        return self.__w3.eth.contract(address=tx_receipt["contractAddress"], abi=abi)  # type: ignore


    def call_test(self, contract, selector: HexStr, arguments: Iterable, params: TxParams) -> Any:
        func = contract.get_function_by_selector(selector)(*arguments)
        return func.call(params)

    
    def fallback(self, contract, data: bytes, params: TxParams, return_tx: bool, request_type: RequestType) -> Any:
        if not params:
            params = {}
        #if no from address is specified, use the default account
        if not "from" in params:
            params['from'] = self.__w3.eth.default_account
        #set the to address to the value of contract on which the fallback function is called
        params['to'] = contract.address
        if data:
            params['data'] =  data #eth_abi.encode(*arguments, *types) #eth_abi.encode(['uint256', 'address'], [666, contract.address]) #self.__w3.eth.default_account])
        #TODO process the transaction inside the devhcain class and return
        tx_hash = self.__w3.eth.send_transaction(params)
        output = self.dev_chain.retrieve_transaction_data([], tx_hash, request_type)
        print(f"type of output: {type(output)}")
        return bytes.fromhex(output)


    def transact(self, contract: web3.contract.Contract, selector: HexStr, arguments: Iterable, params: TxParams, return_tx, request_type) -> Any:
        #print("making a transaction")
        #start_time = time.time()
        func = contract.get_function_by_selector(selector)(*arguments)
        output_abi = get_abi_output_types(func.abi)
        tx_hash = func.transact(params)
        output = self.dev_chain.retrieve_transaction_data([], tx_hash, request_type)
        return eth_abi.abi.decode(output_abi, bytes.fromhex(output))  # type: ignore

    def create_factory(self, addr: AnyAddress, abi) -> web3.contract.Contract:
        return self.__w3.eth.contract(abi=abi, address=addr)  


dev_interface = DevchainInterface(8545)

class Contract:
    abi: Any
    bytecode: HexStr
    address: AnyAddress
    _contract: web3.contract.Contract

    def __init__(self, addr: AnyAddress,  contract: Optional[web3.contract.Contract]):
        self.address = addr
        if not contract:
            self._contract = dev_interface.create_factory(addr, self.abi)
        else:
            self._contract = contract

    @classmethod
    #TODO add option to deploy using a different instance of web3
    def deploy(
        cls, arguments: Iterable, params: Optional[TxParams] = None
    ) -> web3.contract.Contract:
        contract = dev_interface.deploy(cls.abi, cls.bytecode, arguments)
        print(f"the cls is: {cls}")
        return cls(contract.address, contract)


    def transact(self, selector: HexStr, arguments: Iterable, params: TxParams, return_tx: bool, request_type: RequestType) -> Any:
        #print("making a transaction")
        if return_tx:
            raise NotImplementedError("returning a transaction is not implemented")

        return dev_interface.transact(self._contract, selector, arguments, params, return_tx, request_type)


    #TODO handle return data
    def fallback_handler(self, arguments: Iterable, params: TxParams, return_tx: bool, request_type: RequestType) -> Any:
        return dev_interface.fallback(self._contract, arguments[0] if arguments else None, params, return_tx, request_type)


    def call(self, selector: HexStr, arguments: Iterable, params: TxParams, return_tx: bool) -> Any:
        if return_tx:
            raise ValueError("transaction can't be returned from a call")
        #print("making a call")
        #start = time.time()
        output = dev_interface.call_test(self._contract, selector, arguments, params)
        #print(f"call val: {output}")
        #print(f"call: {time.time()-start}")
        return output
