from typing import Any, Iterable, Optional, Type
from enum import IntEnum

import eth_abi
import web3.contract
from eth_typing import HexStr
from web3 import Web3
from web3._utils.abi import get_abi_output_types
from web3.types import TxParams, RPCEndpoint
from web3.method import Method

import time

class NetworkKind(IntEnum):
    ANVIL = 0,
    HARDHAT = 1,
    GANACHE = 2,
    GETH = 3


#global interface for communicating with the devchain
class DevchainInterface:
    __network: NetworkKind
    __port: int
    __w3: Web3

    def __init__(self, port: int):
        self.__port = port
        #self.__w3 = Web3(Web3.WebsocketProvider(f"ws://127.0.0.1:{str(port)}", websocket_timeout=60))
        self.__w3 = Web3(Web3.HTTPProvider(f"http://127.0.0.1:{str(port)}"))
        self.__w3.eth.attach_methods({
            "trace_transaction": Method(RPCEndpoint("trace_transaction")),
            # TODO call
            "debug_trace_transaction": Method(RPCEndpoint("debug_traceTransaction")),
            "anvil_enable_traces": Method(RPCEndpoint("anvil_enableTraces")),  # currently not implemented in anvil - ValueError: {'code': -32603, 'message': 'Not implemented'}
        })
        client_version: str = self.__w3.clientVersion.lower()
        print(f"client version: {client_version}")
        if "anvil" in client_version:
            self.__network = NetworkKind.ANVIL
        elif "hardhat" in client_version:
            self.__network = NetworkKind.HARDHAT
        elif "ethereumjs" in client_version:
            self.__network = NetworkKind.GANACHE
        else:
            self.__network = NetworkKind.GETH
        



    #property
    #def web3(self):
    #    return self.__w3

    def deploy(self, abi, bytecode, params: Optional[TxParams] = None) -> web3.contract.Contract:
        factory = self.__w3.eth.contract(abi=abi, bytecode=bytecode)
        tx_hash = factory.constructor().transact(params)
        tx_receipt = self.__w3.eth.wait_for_transaction_receipt(tx_hash)
        return self.__w3.eth.contract(address=tx_receipt["contractAddress"], abi=abi)  # type: ignore


    def call_test(self, contract, selector: HexStr, arguments: Iterable, params: TxParams) -> Any:
        func = contract.get_function_by_selector(selector)(*arguments)
        return func.call(params)


    def transact(self, contract, selector: HexStr, arguments: Iterable, params: TxParams) -> Any:
        #start_time = time.time()
        func = contract.get_function_by_selector(selector)(*arguments)
        output_abi = get_abi_output_types(func.abi)

        #test of basic call with no creation
        #print(time.time() - start_time)
        # priorities:
        # 1. anvil_enableTraces
        # 2. trace_transaction
        # 3. call
        # 4. debug_traceTransaction

        #start_time = time.time()
        tx_hash = func.transact(params)
        #print(time.time() - start_time)

        #start_time = time.time()
        output = None
        if self.__network == NetworkKind.ANVIL:
            output = self.__w3.eth.trace_transaction(HexStr(tx_hash.hex())) # type: ignore
            while not output:
                output = self.__w3.eth.trace_transaction(HexStr(tx_hash.hex())) # type: ignore
            output = output[0].result.output[2:]

        #print(self.__w3.eth.trace_transaction(HexStr(tx_hash.hex())))  # type: ignore
        elif self.__network == NetworkKind.HARDHAT:
            #output = self.__w3.eth.debug_trace_transaction(HexStr(tx_hash.hex()), {'disableMemory': True, 'disableStack': True, 'disableStorage': True }) # type: ignore
            output = self.__w3.eth.debug_trace_transaction(HexStr(tx_hash.hex()))
            while not output:
                #output = self.__w3.eth.debug_trace_transaction(HexStr(tx_hash.hex()), {'disableMemory': True, 'disableStack': True, 'disableStorage': True }) # type: ignore
                output = self.__w3.eth.debug_trace_transaction(HexStr(tx_hash.hex()))
                #output = self.__w3.eth.trace_transaction(HexStr(tx_hash.hex()))
            output = output.returnValue
        #print(time.time() - start_time)
        return eth_abi.abi.decode(output_abi, bytes.fromhex(output))  # type: ignore


dev_interface = DevchainInterface(8545)


class Contract:
    abi: Any
    bytecode: HexStr
    _contract: web3.contract.Contract

    def __init__(self, contract: web3.contract.Contract):
        self._contract = contract

    @classmethod
    #TODO add option to deploy using a different instance of web3
    def deploy(
        cls, params: Optional[TxParams] = None
    ) -> web3.contract.Contract:
        return cls(dev_interface.deploy(cls.abi, cls.bytecode))  # type: ignore


    def transact(self, selector: HexStr, arguments: Iterable, params: TxParams) -> Any:
        #print(dev_interface.call_test(self._contract, selector, arguments, params))
        return dev_interface.transact(self._contract, selector, arguments, params)
