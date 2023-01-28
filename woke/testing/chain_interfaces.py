from __future__ import annotations

import subprocess
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union
from urllib.error import URLError

from woke.config import WokeConfig

from ..utils.networking import get_free_port
from .globals import get_config
from .json_rpc.communicator import JsonRpcCommunicator, TxParams


class ChainInterfaceAbc(ABC):
    _config: WokeConfig
    _communicator: JsonRpcCommunicator
    _process: Optional[subprocess.Popen]

    def __init__(
        self,
        config: WokeConfig,
        communicator: JsonRpcCommunicator,
        process: Optional[subprocess.Popen] = None,
    ) -> None:
        self._config = config
        self._communicator = communicator
        self._process = process

    @classmethod
    def launch(cls) -> ChainInterfaceAbc:
        config = get_config()

        if config.testing.cmd == "anvil":
            args = ["anvil"] + config.testing.anvil.cmd_args.split()
            constructor = AnvilChainInterface
        elif config.testing.cmd == "ganache":
            args = ["ganache"] + config.testing.ganache.cmd_args.split()
            constructor = GanacheChainInterface
        elif config.testing.cmd == "hardhat":
            args = ["npx", "hardhat", "node"] + config.testing.hardhat.cmd_args.split()
            constructor = HardhatChainInterface
        else:
            raise NotImplementedError(f"Network {config.testing.cmd} not supported")

        hostname = "127.0.0.1"
        port = None
        for i, arg in enumerate(args):
            if arg in {"--port", "-p", "--server.port"}:
                try:
                    port = args[i + 1]
                except IndexError:
                    port = "8545"
            elif arg in {"--hostname", "-h", "--host", "--server.hostname"}:
                try:
                    hostname = args[i + 1]
                except IndexError:
                    hostname = "127.0.0.1"

        if port is None:
            port = str(get_free_port())
            args += ["--port", port]

        print(f"Launching {' '.join(args)}")
        process = subprocess.Popen(
            args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

        try:
            start = time.perf_counter()
            while True:
                try:
                    comm = JsonRpcCommunicator(config, f"ws://{hostname}:{port}")
                    comm.__enter__()
                    comm.web3_client_version()
                    break
                except (ConnectionRefusedError, URLError, ValueError):
                    if time.perf_counter() - start > config.testing.timeout:
                        raise
                    time.sleep(0.05)

            return constructor(config, comm, process)
        except Exception:
            if process.returncode is None:
                process.terminate()
                try:
                    process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
            raise

    @classmethod
    def connect(cls, uri: str) -> ChainInterfaceAbc:
        config = get_config()
        communicator = JsonRpcCommunicator(config, uri)
        communicator.__enter__()
        try:
            client_version = communicator.web3_client_version().lower()
            if "anvil" in client_version:
                return AnvilChainInterface(config, communicator)
            elif "hardhat" in client_version:
                return HardhatChainInterface(config, communicator)
            elif "ethereumjs" in client_version:
                return GanacheChainInterface(config, communicator)
            else:
                raise NotImplementedError(
                    f"Client version {client_version} not supported"
                )
        except Exception:
            communicator.__exit__(None, None, None)
            raise

    def close(self) -> None:
        self._communicator.__exit__(None, None, None)
        if self._process is not None:
            self._process.terminate()
            try:
                self._process.communicate(timeout=self._config.testing.timeout)
            except subprocess.TimeoutExpired:
                self._process.kill()

    def get_balance(self, address: str) -> int:
        return self._communicator.eth_get_balance(address)

    def get_code(
        self, address: str, block_identifier: Union[int, str] = "latest"
    ) -> bytes:
        return self._communicator.eth_get_code(address, block_identifier)

    def accounts(self) -> List[str]:
        return self._communicator.eth_accounts()

    def get_coinbase(self) -> str:
        return self._communicator.eth_coinbase()

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

    def debug_trace_transaction(self, tx_hash: str, options: Dict) -> Dict[str, Any]:
        return self._communicator.debug_trace_transaction(tx_hash, options)

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
    def set_coinbase(self, address: str) -> None:
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

    @abstractmethod
    def set_next_block_timestamp(self, timestamp: int) -> None:
        ...


class HardhatChainInterface(ChainInterfaceAbc):
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

    def set_coinbase(self, address: str) -> None:
        self._communicator.hardhat_set_coinbase(address)

    def get_automine(self) -> bool:
        return self._communicator.hardhat_get_automine()

    def set_automine(self, value: bool) -> None:
        self._communicator.evm_set_automine(value)

    def set_code(self, address: str, value: bytes) -> None:
        self._communicator.hardhat_set_code(address, value)

    def set_nonce(self, address: str, value: int) -> None:
        self._communicator.hardhat_set_nonce(address, value)

    def set_next_block_timestamp(self, timestamp: int) -> None:
        self._communicator.evm_set_next_block_timestamp(timestamp)


class AnvilChainInterface(ChainInterfaceAbc):
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
        self._communicator.anvil_reset()

    def set_coinbase(self, address: str) -> None:
        self._communicator.anvil_set_coinbase(address)

    def get_automine(self) -> bool:
        return self._communicator.anvil_get_automine()

    def set_automine(self, value: bool) -> None:
        self._communicator.evm_set_automine(value)

    def set_code(self, address: str, value: bytes) -> None:
        self._communicator.anvil_set_code(address, value)

    def set_nonce(self, address: str, value: int) -> None:
        self._communicator.anvil_set_nonce(address, value)

    def set_next_block_timestamp(self, timestamp: int) -> None:
        self._communicator.evm_set_next_block_timestamp(timestamp)


class GanacheChainInterface(ChainInterfaceAbc):
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

    def set_coinbase(self, address: str) -> None:
        raise NotImplementedError("Ganache does not support setting coinbase")

    def get_automine(self) -> bool:
        raise NotImplementedError("Ganache does not support automine")

    def set_automine(self, value: bool) -> None:
        raise NotImplementedError("Ganache does not support automine")

    def set_code(self, address: str, value: bytes) -> None:
        return self._communicator.evm_set_account_code(address, value)

    def set_nonce(self, address: str, value: int) -> None:
        return self._communicator.evm_set_account_nonce(address, value)

    def set_next_block_timestamp(self, timestamp: int) -> None:
        raise NotImplementedError(
            "Ganache does not support setting next block timestamp"
        )
