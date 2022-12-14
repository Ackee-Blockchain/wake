from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union

from .json_rpc.communicator import JsonRpcCommunicator, TxParams


class DevChainABC(ABC):
    _communicator: JsonRpcCommunicator

    def __init__(self, communicator: JsonRpcCommunicator) -> None:
        self._communicator = communicator

    def get_balance(self, address: str) -> int:
        return self._communicator.eth_get_balance(address)

    def get_code(self, address: str) -> bytes:
        return self._communicator.eth_get_code(address)

    def accounts(self) -> List[str]:
        return self._communicator.eth_accounts()

    def get_block(
        self, block_identifier: Union[int, str], include_transactions: bool = False
    ) -> Dict[str, Any]:
        return self._communicator.eth_get_block_by_number(
            block_identifier, include_transactions
        )

    def get_block_number(self) -> int:
        return self._communicator.eth_block_number()

    def get_transaction(self, tx_hash: str) -> Dict[str, Any]:
        return self._communicator.eth_get_transaction_by_hash(tx_hash)

    def get_chain_id(self) -> int:
        return self._communicator.eth_chain_id()

    def get_gas_price(self) -> int:
        return self._communicator.eth_gas_price()

    def get_transaction_count(self, address: str) -> int:
        return self._communicator.eth_get_transaction_count(address)

    def get_transaction_receipt(self, tx_hash: str) -> Optional[Dict[str, Any]]:
        return self._communicator.eth_get_transaction_receipt(tx_hash)

    def call(self, params: TxParams) -> bytes:
        return self._communicator.eth_call(params)

    def estimate_gas(self, params: TxParams) -> int:
        return self._communicator.eth_estimate_gas(params)

    def send_transaction(self, params: TxParams) -> str:
        return self._communicator.eth_send_transaction(params)

    def debug_trace_transaction(self, tx_hash: str, options: Dict) -> Dict:
        return self._communicator.debug_trace_transaction(tx_hash, options)

    def wait_for_transaction_receipt(self, tx_hash: str) -> Dict[str, Any]:
        ret = self._communicator.eth_get_transaction_receipt(tx_hash)
        while ret is None:
            ret = self._communicator.eth_get_transaction_receipt(tx_hash)
        return ret

    def snapshot(self) -> str:
        return self._communicator.evm_snapshot()

    def revert(self, snapshot_id: str) -> bool:
        return self._communicator.evm_revert(snapshot_id)

    def mine(self, timestamp: Optional[int]) -> None:
        self._communicator.evm_mine(timestamp)

    @abstractmethod
    def get_automine(self) -> bool:
        ...

    @abstractmethod
    def set_automine(self, value: bool) -> None:
        ...

    @abstractmethod
    def reset(self) -> None:
        ...

    @abstractmethod
    def set_balance(self, address: str, value: int) -> None:
        ...

    @abstractmethod
    def set_block_gas_limit(self, gas_limit: int) -> None:
        ...

    @abstractmethod
    def set_code(self, address: str, value: bytes) -> None:
        ...

    @abstractmethod
    def set_nonce(self, address: str, value: int) -> None:
        ...


class HardhatDevChain(DevChainABC):
    def set_balance(self, address: str, value: int) -> None:
        self._communicator.hardhat_set_balance(address, value)

    def impersonate_account(self, address: str) -> None:
        self._communicator.hardhat_impersonate_account(address)

    def stop_impersonating_account(self, address: str) -> None:
        self._communicator.hardhat_stop_impersonating_account(address)

    def set_block_gas_limit(self, gas_limit: int) -> None:
        self._communicator.evm_set_block_gas_limit(gas_limit)

    def reset(self) -> None:
        self._communicator.hardhat_reset()

    def get_automine(self) -> bool:
        return self._communicator.hardhat_get_automine()

    def set_automine(self, value: bool) -> None:
        self._communicator.evm_set_automine(value)

    def set_code(self, address: str, value: bytes) -> None:
        self._communicator.hardhat_set_code(address, value)

    def set_nonce(self, address: str, value: int) -> None:
        self._communicator.hardhat_set_nonce(address, value)


class AnvilDevChain(DevChainABC):
    def trace_transaction(self, tx_hash: Any) -> List:
        return self._communicator.trace_transaction(tx_hash)

    def set_balance(self, address: str, value: int) -> None:
        self._communicator.anvil_set_balance(address, value)

    def impersonate_account(self, address: str) -> None:
        self._communicator.anvil_impersonate_account(address)

    def stop_impersonating_account(self, address: str) -> None:
        self._communicator.anvil_stop_impersonating_account(address)

    def set_block_gas_limit(self, gas_limit: int) -> None:
        self._communicator.evm_set_block_gas_limit(gas_limit)

    def reset(self) -> None:
        raise NotImplementedError("Anvil does not support resetting the chain")
        self._communicator.anvil_reset()

    def get_automine(self) -> bool:
        return self._communicator.anvil_get_automine()

    def set_automine(self, value: bool) -> None:
        self._communicator.evm_set_automine(value)

    def set_code(self, address: str, value: bytes) -> None:
        self._communicator.anvil_set_code(address, value)

    def set_nonce(self, address: str, value: int) -> None:
        self._communicator.anvil_set_nonce(address, value)


class GanacheDevChain(DevChainABC):
    def set_balance(self, address: str, value: int) -> None:
        self._communicator.evm_set_account_balance(address, value)

    def add_account(self, address: str, passphrase: str) -> bool:
        return self._communicator.evm_add_account(
            address, passphrase
        ) and self._communicator.personal_unlock_account(address, passphrase, 0)

    def set_block_gas_limit(self, gas_limit: int) -> None:
        raise NotImplementedError("Ganache does not support setting block gas limit")

    def reset(self) -> None:
        raise NotImplementedError("Ganache does not support resetting the chain")

    def get_automine(self) -> bool:
        raise NotImplementedError("Ganache does not support automine")

    def set_automine(self, value: bool) -> None:
        raise NotImplementedError("Ganache does not support automine")

    def set_code(self, address: str, value: bytes) -> None:
        return self._communicator.evm_set_account_code(address, value)

    def set_nonce(self, address: str, value: int) -> None:
        return self._communicator.evm_set_account_nonce(address, value)
