from abc import ABC, abstractmethod
from enum import IntEnum
from typing import Any, Callable, Dict, List

from eth_typing import HexStr
from web3 import Web3
from web3.method import Method
from web3.types import RPCEndpoint

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

    @abstractmethod
    def get_balance(self, address: str) -> int:
        ...

    @abstractmethod
    def set_balance(self, address: str, value: int) -> None:
        ...


class HardhatDevChain(DevChainABC):
    def __init__(self, w3: Web3):
        super().__init__(w3)
        self.w3.eth.attach_methods(
            {
                "debug_trace_transaction": Method(
                    RPCEndpoint("debug_traceTransaction")
                ),
                "hardhat_set_balance": Method(RPCEndpoint("hardhat_setBalance")),
            }
        )

    def retrieve_transaction_data(
        self, params: List, tx_hash: Any, request_type: RequestType
    ) -> str:
        if request_type == RequestType.DEFAULT:
            output = self.w3.eth.debug_trace_transaction(HexStr(tx_hash.hex()), {"disableMemory": True, "disableStack": True, "disableStorage": True})  # type: ignore
            output = output.returnValue
        else:
            raise NotImplementedError()
        return output

    def get_balance(self, address: str) -> int:
        return self.w3.eth.get_balance(address)

    def set_balance(self, address: str, value: int) -> None:
        self.w3.eth.hardhat_set_balance(
            address, hex(value)
        )  # pyright: reportGeneralTypeIssues=false


class AnvilDevChain(DevChainABC):
    def __init__(self, w3: Web3):
        super().__init__(w3)
        self.w3.eth.attach_methods(
            {
                "trace_transaction": Method(RPCEndpoint("trace_transaction")),
                "debug_trace_transaction": Method(
                    RPCEndpoint("debug_traceTransaction")
                ),
                "anvil_enable_traces": Method(
                    RPCEndpoint("anvil_enableTraces")
                ),  # currently not implemented in anvil - ValueError: {'code': -32603, 'message': 'Not implemented'}
                "anvil_set_balance": Method(RPCEndpoint("anvil_setBalance")),
            }
        )

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

    def get_balance(self, address: str) -> int:
        return self.w3.eth.get_balance(address)

    def set_balance(self, address: str, value: int) -> None:
        self.w3.eth.anvil_set_balance(
            address, hex(value)
        )  # pyright: reportGeneralTypeIssues=false


class GanacheDevChain(DevChainABC):
    def __init__(self, w3: Web3):
        super().__init__(w3)
        self.w3.eth.attach_methods(
            {
                "debug_trace_transaction": Method(
                    RPCEndpoint("debug_traceTransaction")
                ),
                "evm_set_account_balance": Method(RPCEndpoint("evm_setAccountBalance")),
            }
        )

    def retrieve_transaction_data(
        self, params: List, tx_hash: Any, request_type: RequestType
    ) -> str:
        if request_type == RequestType.DEFAULT:
            output = self.w3.eth.debug_trace_transaction(HexStr(tx_hash.hex()), {"disableMemory": True, "disableStack": True, "disableStorage": True})  # type: ignore
            output = output.returnValue
        else:
            raise NotImplementedError()
        return output

    def get_balance(self, address: str) -> int:
        return self.w3.eth.get_balance(address)

    def set_balance(self, address: str, value: int) -> None:
        self.w3.eth.evm_set_account_balance(
            address, hex(value)
        )  # pyright: reportGeneralTypeIssues=false
