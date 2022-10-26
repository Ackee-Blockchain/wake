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

    @abstractmethod
    def set_block_gas_limit(self, gas_limit: int) -> None:
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
                "hardhat_impersonate_account": Method(
                    RPCEndpoint("hardhat_impersonateAccount")
                ),
                "hardhat_stop_impersonating_account": Method(
                    RPCEndpoint("hardhat_stopImpersonatingAccount")
                ),
                "evm_set_block_gas_limit": Method(RPCEndpoint("evm_setBlockGasLimit")),
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

    def impersonate_account(self, address: str) -> None:
        self.w3.eth.hardhat_impersonate_account(address)

    def stop_impersonating_account(self, address: str) -> None:
        self.w3.eth.hardhat_stop_impersonating_account(address)

    def set_block_gas_limit(self, gas_limit: int) -> None:
        self.w3.eth.evm_set_block_gas_limit(hex(gas_limit))


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
                "anvil_impersonate_account": Method(
                    RPCEndpoint("anvil_impersonateAccount")
                ),
                "anvil_stop_impersonating_account": Method(
                    RPCEndpoint("anvil_stopImpersonatingAccount")
                ),
                "evm_set_block_gas_limit": Method(RPCEndpoint("evm_setBlockGasLimit")),
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

    def impersonate_account(self, address: str) -> None:
        self.w3.eth.anvil_impersonate_account(address)

    def stop_impersonating_account(self, address: str) -> None:
        self.w3.eth.anvil_stop_impersonating_account(address)

    def set_block_gas_limit(self, gas_limit: int) -> None:
        self.w3.eth.evm_set_block_gas_limit(hex(gas_limit))


class GanacheDevChain(DevChainABC):
    def __init__(self, w3: Web3):
        super().__init__(w3)
        self.w3.eth.attach_methods(
            {
                "debug_trace_transaction": Method(
                    RPCEndpoint("debug_traceTransaction")
                ),
                "evm_set_account_balance": Method(RPCEndpoint("evm_setAccountBalance")),
                "evm_add_account": Method(RPCEndpoint("evm_addAccount")),
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

    def add_account(self, address: str, passphrase: str) -> bool:
        return self.w3.eth.evm_add_account(address, passphrase)

    def set_block_gas_limit(self, gas_limit: int) -> None:
        raise NotImplementedError("Ganache does not support setting block gas limit")
