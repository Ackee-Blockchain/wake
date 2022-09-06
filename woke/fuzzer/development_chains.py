from abc import ABC, abstractmethod

from eth_typing import HexStr
from typing import Callable, List, Dict, Any

from enum import IntEnum

from web3 import Web3


class RequestKind(IntEnum):
    ANVIL_ENABLE_TRACES = 0
    TRACE_TRANSACTION = 1
    DEBUG_TRACE_TRANSACTION = 2
    CALL = 3


class DevChainABC(ABC):
    w3: Web3

    @abstractmethod
    def __init__(self, w3: Web3) -> None:
        self.w3 = w3

    @abstractmethod
    def retrieve_transaction(self, method: RequestKind, params: List, tx_hash: Any) -> Dict:
        raise NotImplementedError


class HardhatDevChain(DevChainABC):
    def __init__(self, w3: Web3):
        DevChainABC.__init__(self, w3)

    def retrieve_transaction(self, method: str, params: List, tx_hash: Any) -> Dict:
        output = None
        if method == RequestKind.DEBUG_TRACE_TRANSACTION:
            #output = self.w3.eth.debug_trace_transaction(HexStr(tx_hash.hex()))
            output = self.w3.eth.debug_trace_transaction(HexStr(tx_hash.hex()), {'disableMemory': True, 'disableStack': True, 'disableStorage': True }) # type: ignore
            #while not output:
                #output = self.w3.eth.debug_trace_transaction(HexStr(tx_hash.hex()))
                #output = self.__w3.eth.trace_transaction(HexStr(tx_hash.hex()))
            output = output.returnValue
        else:
            #TODO throw exception
            pass
        return output
        

class AnvilDevChain(DevChainABC):
    def __init__(self, w3: Web3):
        DevChainABC.__init__(self, w3)

    def retrieve_transaction(self, method: str, params: List, tx_hash: Any) -> Dict:
        output = None
        if method == RequestKind.TRACE_TRANSACTION:
            output = self.w3.eth.trace_transaction(HexStr(tx_hash.hex())) # type: ignore
            while not output:
                output = self.w3.eth.trace_transaction(HexStr(tx_hash.hex())) # type: ignore
            output = output[0].result.output[2:]
        else:
            #TODO trow exception
            pass
        return output 
