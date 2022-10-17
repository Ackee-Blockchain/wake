from abc import ABC, abstractmethod
from enum import IntEnum
from typing import Any, Callable, Dict, List

from eth_typing import HexStr
from web3 import Web3

from woke.fuzzer.abi_to_type import RequestType


class DevChainABC(ABC):
    w3: Web3

    @abstractmethod
    def __init__(self, w3: Web3) -> None:
        self.w3 = w3

    @abstractmethod
    def retrieve_transaction_data(
        self, params: List, tx_hash: Any, request_type: RequestType
    ) -> str:
        ...


class HardhatDevChain(DevChainABC):
    def __init__(self, w3: Web3):
        DevChainABC.__init__(self, w3)

    def retrieve_transaction_data(
        self, params: List, tx_hash: Any, request_type: RequestType
    ) -> str:
        if request_type == RequestType.DEFAULT:
            output = self.w3.eth.debug_trace_transaction(HexStr(tx_hash.hex()), {"disableMemory": True, "disableStack": True, "disableStorage": True})  # type: ignore
            output = output.returnValue
        else:
            raise NotImplementedError()
        return output


class AnvilDevChain(DevChainABC):
    def __init__(self, w3: Web3):
        DevChainABC.__init__(self, w3)

    def retrieve_transaction_data(
        self, params: List, tx_hash: Any, request_type: RequestType
    ) -> str:
        if request_type == RequestType.DEFAULT:
            output = self.w3.eth.trace_transaction(HexStr(tx_hash.hex()))  # type: ignore
            while not output:
                output = self.w3.eth.trace_transaction(HexStr(tx_hash.hex()))  # type: ignore
            output = output[0].result.output[2:]
        else:
            raise NotImplementedError()
        return output


class GanacheDevChain(DevChainABC):
    def __init__(self, w3: Web3):
        DevChainABC.__init__(self, w3)

    def retrieve_transaction_data(
        self, params: List, tx_hash: Any, request_type: RequestType
    ) -> str:
        if request_type == RequestType.DEFAULT:
            output = self.w3.eth.debug_trace_transaction(HexStr(tx_hash.hex()), {"disableMemory": True, "disableStack": True, "disableStorage": True})  # type: ignore
            output = output.returnValue
        else:
            raise NotImplementedError()
        return output
