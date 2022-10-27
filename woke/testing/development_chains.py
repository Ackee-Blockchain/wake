import asyncio
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Union

from .json_rpc.communicator import JsonRpcCommunicator, TxParams


class DevChainABC(ABC):
    _loop: asyncio.AbstractEventLoop
    _communicator: JsonRpcCommunicator

    def __init__(
        self, loop: asyncio.AbstractEventLoop, communicator: JsonRpcCommunicator
    ) -> None:
        self._loop = loop
        self._communicator = communicator

    @abstractmethod
    def retrieve_transaction_data(self, params: List, tx_hash: str) -> bytes:
        ...

    def get_balance(self, address: str) -> int:
        return self._loop.run_until_complete(
            self._communicator.eth_get_balance(address)
        )

    def accounts(self) -> List[str]:
        return self._loop.run_until_complete(self._communicator.eth_accounts())

    def get_block(self, block_identifier: Union[int, str]) -> Dict[str, Any]:
        return self._loop.run_until_complete(
            self._communicator.eth_get_block_by_number(block_identifier, False)
        )

    def get_chain_id(self) -> int:
        return self._loop.run_until_complete(self._communicator.eth_chain_id())

    def get_transaction_count(self, address: str) -> int:
        return self._loop.run_until_complete(
            self._communicator.eth_get_transaction_count(address)
        )

    def call(self, params: TxParams) -> bytes:
        return self._loop.run_until_complete(self._communicator.eth_call(params))

    def estimate_gas(self, params: TxParams) -> int:
        return self._loop.run_until_complete(
            self._communicator.eth_estimate_gas(params)
        )

    def send_transaction(self, params: TxParams) -> str:
        return self._loop.run_until_complete(
            self._communicator.eth_send_transaction(params)
        )

    def wait_for_transaction_receipt(self, tx_hash: str) -> Dict[str, Any]:
        ret = self._loop.run_until_complete(
            self._communicator.eth_get_transaction_receipt(tx_hash)
        )
        while ret is None:
            ret = self._loop.run_until_complete(
                self._communicator.eth_get_transaction_receipt(tx_hash)
            )
        return ret

    @abstractmethod
    def set_balance(self, address: str, value: int) -> None:
        ...

    @abstractmethod
    def set_block_gas_limit(self, gas_limit: int) -> None:
        ...


class HardhatDevChain(DevChainABC):
    def retrieve_transaction_data(self, params: List, tx_hash: str) -> bytes:
        options = {"disableMemory": True, "disableStack": True, "disableStorage": True}
        output = self._loop.run_until_complete(
            self._communicator.debug_trace_transaction(tx_hash, options)
        )
        return bytes.fromhex(output["returnValue"])

    def set_balance(self, address: str, value: int) -> None:
        self._loop.run_until_complete(
            self._communicator.hardhat_set_balance(address, value)
        )

    def impersonate_account(self, address: str) -> None:
        self._loop.run_until_complete(
            self._communicator.hardhat_impersonate_account(address)
        )

    def stop_impersonating_account(self, address: str) -> None:
        self._loop.run_until_complete(
            self._communicator.hardhat_stop_impersonating_account(address)
        )

    def set_block_gas_limit(self, gas_limit: int) -> None:
        self._loop.run_until_complete(
            self._communicator.evm_set_block_gas_limit(gas_limit)
        )


class AnvilDevChain(DevChainABC):
    def retrieve_transaction_data(self, params: List, tx_hash: Any) -> bytes:
        output = self._loop.run_until_complete(
            self._communicator.trace_transaction(tx_hash)
        )
        return bytes.fromhex(output[0]["result"]["output"][2:])

    def set_balance(self, address: str, value: int) -> None:
        self._loop.run_until_complete(
            self._communicator.anvil_set_balance(address, value)
        )

    def impersonate_account(self, address: str) -> None:
        self._loop.run_until_complete(
            self._communicator.anvil_impersonate_account(address)
        )

    def stop_impersonating_account(self, address: str) -> None:
        self._loop.run_until_complete(
            self._communicator.anvil_stop_impersonating_account(address)
        )

    def set_block_gas_limit(self, gas_limit: int) -> None:
        self._loop.run_until_complete(
            self._communicator.evm_set_block_gas_limit(gas_limit)
        )


class GanacheDevChain(DevChainABC):
    def retrieve_transaction_data(self, params: List, tx_hash: Any) -> bytes:
        options = {"disableMemory": True, "disableStack": True, "disableStorage": True}
        output = self._loop.run_until_complete(
            self._communicator.debug_trace_transaction(tx_hash, options)
        )
        return bytes.fromhex(output["returnValue"])

    def set_balance(self, address: str, value: int) -> None:
        self._loop.run_until_complete(
            self._communicator.evm_set_account_balance(address, value)
        )

    def add_account(self, address: str, passphrase: str) -> bool:
        return self._loop.run_until_complete(
            self._communicator.evm_add_account(address, passphrase)
        ) and self._loop.run_until_complete(
            self._communicator.personal_unlock_account(address, passphrase, 0)
        )

    def set_block_gas_limit(self, gas_limit: int) -> None:
        raise NotImplementedError("Ganache does not support setting block gas limit")
