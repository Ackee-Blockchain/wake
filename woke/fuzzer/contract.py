from multiprocessing.sharedctypes import Value
from typing import Any, Iterable, Optional, Type, overload
from enum import IntEnum

import eth_abi
import web3.contract
from eth_typing import HexStr
from web3 import Web3
from web3._utils.abi import get_abi_output_types
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


#global interface for communicating with the devchain
class DevchainInterface:
    #__network: NetworkKind
    __dev_chain: DevChainABC
    __port: int
    __w3: Web3

    def __init__(self, port: int):
        self.__port = port
        self.__w3 = Web3(Web3.WebsocketProvider(f"ws://127.0.0.1:{str(port)}", websocket_timeout=60))
        #self.__w3 = Web3(Web3.HTTPProvider(f"http://127.0.0.1:{str(port)}"))
        self.__w3.eth.attach_methods({
            "trace_transaction": Method(RPCEndpoint("trace_transaction")),
            # TODO call
            "debug_trace_transaction": Method(RPCEndpoint("debug_traceTransaction")),
            "anvil_enable_traces": Method(RPCEndpoint("anvil_enableTraces")),  # currently not implemented in anvil - ValueError: {'code': -32603, 'message': 'Not implemented'}
        })
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


    def transact(self, contract, selector: HexStr, arguments: Iterable, params: TxParams, return_tx, request_type) -> Any:
        #start_time = time.time()
        func = contract.get_function_by_selector(selector)(*arguments)
        output_abi = get_abi_output_types(func.abi)

        # priorities:
        # 1. anvil_enableTraces
        # 2. trace_transaction
        # 3. call
        # 4. debug_traceTransaction

        #start = time.time()
        tx_hash = func.transact(params)
        #print(f"transact: {time.time()-start}")
        
        #method = RequestKind.DEBUG_TRACE_TRANSACTION
        #start = time.time()
        output = self.dev_chain.retrieve_transaction_data([], tx_hash, request_type)
        #print(f"trace: {time.time()-start}")
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
        cls, arguments: Iterable, params: Optional[TxParams] = None
    ) -> web3.contract.Contract:
        return cls(dev_interface.deploy(cls.abi, cls.bytecode, arguments)) 


    def transact(self, selector: HexStr, arguments: Iterable, params: TxParams, return_tx: bool, request_type: RequestType) -> Any:
        #print("making a transaction")
        if return_tx:
            raise NotImplementedError("returning a transaction is not implemented")

        return dev_interface.transact(self._contract, selector, arguments, params, return_tx, request_type)


    #TODO throw if return_tx == True
    def call(self, selector: HexStr, arguments: Iterable, params: TxParams, return_tx: bool) -> Any:
        if return_tx:
            raise ValueError("transaction can't be returned from a call")
        #print("making a call")
        #start = time.time()
        output = dev_interface.call_test(self._contract, selector, arguments, params)
        #print(f"call val: {output}")
        #print(f"call: {time.time()-start}")
        return output
