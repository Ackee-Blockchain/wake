from __future__ import annotations

import subprocess
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union
from urllib.error import URLError

from typing_extensions import Literal, TypedDict

from wake.cli.console import console
from wake.config import WakeConfig
from wake.utils.networking import get_free_port

from .json_rpc.communicator import JsonRpcCommunicator

TxParams = TypedDict(
    "TxParams",
    {
        "type": int,
        "nonce": int,
        "to": str,
        "from": str,
        "gas": Union[int, Literal["auto"]],
        "value": int,
        "data": bytes,
        "gasPrice": int,
        "maxPriorityFeePerGas": int,
        "maxFeePerGas": int,
        "accessList": Union[List, Literal["auto"]],
        "chainId": int,
    },
    total=False,
)


class ChainInterfaceAbc(ABC):
    _config: WakeConfig
    _communicator: JsonRpcCommunicator
    _process: Optional[subprocess.Popen]

    def __init__(
        self,
        config: WakeConfig,
        communicator: JsonRpcCommunicator,
        process: Optional[subprocess.Popen] = None,
    ) -> None:
        self._config = config
        self._communicator = communicator
        self._process = process

    @staticmethod
    def _encode_tx_params(transaction: TxParams) -> Dict:
        tx = {}
        if "type" in transaction:
            tx["type"] = hex(transaction["type"])
        if "nonce" in transaction:
            tx["nonce"] = hex(transaction["nonce"])
        if "to" in transaction:
            tx["to"] = transaction["to"]
        if "from" in transaction:
            tx["from"] = transaction["from"]
        if "gas" in transaction:
            assert transaction["gas"] != "auto"
            tx["gas"] = hex(transaction["gas"])
        if "value" in transaction:
            tx["value"] = hex(transaction["value"])
        if "data" in transaction:
            tx["data"] = "0x" + transaction["data"].hex()
        if "gasPrice" in transaction:
            tx["gasPrice"] = hex(transaction["gasPrice"])
        if "maxPriorityFeePerGas" in transaction:
            tx["maxPriorityFeePerGas"] = hex(transaction["maxPriorityFeePerGas"])
        if "maxFeePerGas" in transaction:
            tx["maxFeePerGas"] = hex(transaction["maxFeePerGas"])
        if "accessList" in transaction:
            assert transaction["accessList"] != "auto"
            tx["accessList"] = transaction["accessList"]
        if "chainId" in transaction:
            tx["chainId"] = hex(transaction["chainId"])
        return tx

    @staticmethod
    def _encode_block_identifier(block_identifier: Union[int, str]) -> str:
        if isinstance(block_identifier, int):
            return hex(block_identifier)
        elif isinstance(block_identifier, str):
            return block_identifier
        else:
            raise TypeError("block identifier must be either int or str")

    @classmethod
    def launch(
        cls,
        config: WakeConfig,
        *,
        accounts: Optional[int] = None,
        chain_id: Optional[int] = None,
        fork: Optional[str] = None,
        hardfork: Optional[str] = None,
    ) -> ChainInterfaceAbc:
        if config.testing.cmd == "anvil":
            args = ["anvil"] + config.testing.anvil.cmd_args.split()
            constructor = AnvilChainInterface
        elif config.testing.cmd == "ganache":
            args = ["ganache"] + config.testing.ganache.cmd_args.split()
            constructor = GanacheChainInterface
        elif config.testing.cmd == "hardhat":
            if (
                accounts is not None
                or chain_id is not None
                or fork is not None
                or hardfork is not None
            ):
                raise ValueError(
                    "Setting accounts, chain_id, fork and hardfork is not supported for hardhat"
                )

            args = ["npx", "hardhat", "node"] + config.testing.hardhat.cmd_args.split()
            constructor = HardhatChainInterface
        else:
            raise NotImplementedError(f"Network {config.testing.cmd} not supported")

        hostname = "127.0.0.1"
        port = None
        accounts_set = False
        chain_id_set = False
        fork_set = False
        hardfork_set = False

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
            elif (
                arg in {"-a", "--accounts", "--wallet.accounts"}
                and accounts is not None
            ):
                accounts_set = True
                try:
                    args[i + 1] = str(accounts)
                except IndexError:
                    args += [str(accounts)]
            elif arg in {"--chain-id", "--chain.chainId"} and chain_id is not None:
                chain_id_set = True
                try:
                    args[i + 1] = str(chain_id)
                except IndexError:
                    args += [str(chain_id)]
            elif (
                arg in {"-f", "--fork-url", "--fork.url", "--rpc-url"}
                and fork is not None
            ):
                fork_set = True
                try:
                    args[i + 1] = fork
                except IndexError:
                    args += [fork]
            elif (
                arg in {"--hardfork", "-k", "--chain.hardfork"} and hardfork is not None
            ):
                hardfork_set = True
                try:
                    args[i + 1] = hardfork
                except IndexError:
                    args += [hardfork]

        if port is None:
            port = str(get_free_port())
            args += ["--port", port]
        if accounts is not None and not accounts_set:
            args += ["-a", str(accounts)]
        if chain_id is not None and not chain_id_set:
            if config.testing.cmd == "anvil":
                args += ["--chain-id", str(chain_id)]
            elif config.testing.cmd == "ganache":
                args += ["--chain.chainId", str(chain_id)]
        if fork is not None and not fork_set:
            args += ["-f", fork]
        if hardfork is not None and not hardfork_set:
            if config.testing.cmd == "anvil":
                args += ["--hardfork", hardfork]
            elif config.testing.cmd == "ganache":
                args += ["-k", hardfork]

        console.print(f"Launching {' '.join(args)}")
        process = subprocess.Popen(args, stdout=subprocess.DEVNULL)

        try:
            start = time.perf_counter()
            while True:
                try:
                    comm = JsonRpcCommunicator(config, f"ws://{hostname}:{port}")
                    comm.__enter__()
                    comm.send_request("web3_clientVersion").lower()
                    break
                except (ConnectionRefusedError, URLError, ValueError):
                    if time.perf_counter() - start > config.general.json_rpc_timeout:
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
    def connect(cls, config: WakeConfig, uri: str) -> ChainInterfaceAbc:
        communicator = JsonRpcCommunicator(config, uri)
        communicator.__enter__()
        try:
            client_version: str = communicator.send_request(
                "web3_clientVersion"
            ).lower()
            chain_id = int(communicator.send_request("eth_chainId"), 16)
            if "anvil" in client_version:
                return AnvilChainInterface(config, communicator)
            elif "hardhat" in client_version:
                return HardhatChainInterface(config, communicator)
            elif "ethereumjs" in client_version:
                return GanacheChainInterface(config, communicator)
            elif client_version.startswith(("geth", "bor")):
                return GethChainInterface(config, communicator)
            elif client_version.startswith("erigon"):
                return ErigonChainInterface(config, communicator)
            elif "nitro" in client_version:
                return NitroChainInterface(config, communicator)
            elif chain_id in {43113, 43114}:
                # Avax client reports just a version number without the name of the client
                # => hard to distinguish from other clients
                return AvalancheChainInterface(config, communicator)
            elif chain_id in {1101, 1442}:
                return HermezChainInterface(config, communicator)
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
                self._process.communicate(timeout=self._config.general.json_rpc_timeout)
            except subprocess.TimeoutExpired:
                self._process.kill()

    def get_client_version(self) -> str:
        return self._communicator.send_request("web3_clientVersion")

    def get_balance(
        self, address: str, block_identifier: Union[int, str] = "latest"
    ) -> int:
        return int(
            self._communicator.send_request(
                "eth_getBalance",
                [address, self._encode_block_identifier(block_identifier)],
            ),
            16,
        )

    def get_code(
        self, address: str, block_identifier: Union[int, str] = "latest"
    ) -> bytes:
        return bytes.fromhex(
            self._communicator.send_request(
                "eth_getCode",
                [address, self._encode_block_identifier(block_identifier)],
            )[2:]
        )

    def get_coinbase(self) -> str:
        return self._communicator.send_request("eth_coinbase")

    def get_block(
        self, block_identifier: Union[int, str], include_transactions: bool = False
    ) -> Dict[str, Any]:
        return self._communicator.send_request(
            "eth_getBlockByNumber",
            [self._encode_block_identifier(block_identifier), include_transactions],
        )

    def get_block_number(self) -> int:
        return int(self._communicator.send_request("eth_blockNumber"), 16)

    def get_transaction(self, tx_hash: str) -> Dict[str, Any]:
        return self._communicator.send_request("eth_getTransactionByHash", [tx_hash])

    def get_chain_id(self) -> int:
        return int(self._communicator.send_request("eth_chainId"), 16)

    def get_gas_price(self) -> int:
        return int(self._communicator.send_request("eth_gasPrice"), 16)

    def get_transaction_count(
        self, address: str, block_identifier: Union[int, str] = "latest"
    ) -> int:
        return int(
            self._communicator.send_request(
                "eth_getTransactionCount",
                [address, self._encode_block_identifier(block_identifier)],
            ),
            16,
        )

    def get_transaction_receipt(self, tx_hash: str) -> Optional[Dict[str, Any]]:
        return self._communicator.send_request("eth_getTransactionReceipt", [tx_hash])

    def call(
        self, params: TxParams, block_identifier: Union[int, str] = "latest"
    ) -> bytes:
        return bytes.fromhex(
            self._communicator.send_request(
                "eth_call",
                [
                    self._encode_tx_params(params),
                    self._encode_block_identifier(block_identifier),
                ],
            )[2:]
        )

    def estimate_gas(
        self, params: TxParams, block_identifier: Union[int, str] = "pending"
    ) -> int:
        return int(
            self._communicator.send_request(
                "eth_estimateGas",
                [
                    self._encode_tx_params(params),
                    self._encode_block_identifier(block_identifier),
                ],
            ),
            16,
        )

    def send_transaction(self, params: TxParams) -> str:
        return self._communicator.send_request(
            "eth_sendTransaction", [self._encode_tx_params(params)]
        )

    def send_raw_transaction(self, raw_tx: bytes) -> str:
        return self._communicator.send_request(
            "eth_sendRawTransaction", ["0x" + raw_tx.hex()]
        )

    def debug_trace_transaction(
        self, tx_hash: str, options: Optional[Dict] = None
    ) -> Dict[str, Any]:
        return self._communicator.send_request(
            "debug_traceTransaction",
            [tx_hash, options] if options is not None else [tx_hash],
        )

    def debug_trace_call(
        self,
        params: TxParams,
        block_identifier: Union[int, str] = "latest",
        options: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        return self._communicator.send_request(
            "debug_traceCall",
            [
                self._encode_tx_params(params),
                self._encode_block_identifier(block_identifier),
                options,
            ]
            if options is not None
            else [
                self._encode_tx_params(params),
                self._encode_block_identifier(block_identifier),
            ],
        )

    def snapshot(self) -> str:
        return self._communicator.send_request("evm_snapshot")

    def revert(self, snapshot_id: str) -> bool:
        return self._communicator.send_request("evm_revert", [snapshot_id])

    def mine(self, timestamp: Optional[int]) -> None:
        self._communicator.send_request(
            "evm_mine", [hex(timestamp)] if timestamp is not None else None
        )

    def get_max_priority_fee_per_gas(self) -> int:
        return int(self._communicator.send_request("eth_maxPriorityFeePerGas"), 16)

    def sign(self, address: str, message: bytes) -> bytes:
        return bytes.fromhex(
            self._communicator.send_request(
                "eth_sign", [address, "0x" + message.hex()]
            )[2:]
        )

    def sign_typed(self, address: str, message: Dict) -> bytes:
        return bytes.fromhex(
            self._communicator.send_request("eth_signTypedData_v4", [address, message])[
                2:
            ]
        )

    def create_access_list(
        self, params: TxParams, block_identifier: Union[int, str] = "pending"
    ) -> Dict[str, Any]:
        return self._communicator.send_request(
            "eth_createAccessList",
            [
                self._encode_tx_params(params),
                self._encode_block_identifier(block_identifier),
            ],
        )

    def trace_transaction(self, tx_hash: str) -> List:
        return self._communicator.send_request("trace_transaction", [tx_hash])

    def get_storage_at(
        self, address: str, position: int, block_identifier: Union[int, str] = "latest"
    ) -> bytes:
        return bytes.fromhex(
            self._communicator.send_request(
                "eth_getStorageAt",
                [
                    address,
                    hex(position),
                    self._encode_block_identifier(block_identifier),
                ],
            )[2:]
        )

    def get_logs(
        self,
        *,
        from_block: Optional[Union[int, str]] = None,
        to_block: Optional[Union[int, str]] = None,
        address: Optional[str] = None,
        topics: Optional[List[str]] = None,
    ) -> List:
        params = {}
        if from_block is not None:
            params["fromBlock"] = self._encode_block_identifier(from_block)
        if to_block is not None:
            params["toBlock"] = self._encode_block_identifier(to_block)
        if address is not None:
            params["address"] = address
        if topics is not None:
            params["topics"] = topics
        return self._communicator.send_request("eth_getLogs", [params])

    @abstractmethod
    def get_accounts(self) -> List[str]:
        ...

    @abstractmethod
    def get_automine(self) -> bool:
        ...

    @abstractmethod
    def set_automine(self, value: bool) -> None:
        ...

    @abstractmethod
    def reset(self, options: Optional[Dict] = None) -> None:
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

    @abstractmethod
    def send_unsigned_transaction(self, params: TxParams) -> str:
        ...

    @abstractmethod
    def set_next_block_base_fee_per_gas(self, value: int) -> None:
        ...

    @abstractmethod
    def set_min_gas_price(self, value: int) -> None:
        ...

    @abstractmethod
    def set_storage_at(self, address: str, position: int, value: bytes) -> None:
        ...

    @abstractmethod
    def mine_many(self, num_blocks: int, timestamp_change: Optional[int]) -> None:
        ...


class HardhatChainInterface(ChainInterfaceAbc):
    def get_accounts(self) -> List[str]:
        return self._communicator.send_request("eth_accounts")

    def set_balance(self, address: str, value: int) -> None:
        self._communicator.send_request("hardhat_setBalance", [address, hex(value)])

    def impersonate_account(self, address: str) -> None:
        self._communicator.send_request("hardhat_impersonateAccount", [address])

    def stop_impersonating_account(self, address: str) -> None:
        self._communicator.send_request("hardhat_stopImpersonatingAccount", [address])

    def set_block_gas_limit(self, gas_limit: int) -> None:
        self._communicator.send_request("evm_setBlockGasLimit", [hex(gas_limit)])

    def reset(self, options: Optional[Dict] = None) -> None:
        self._communicator.send_request(
            "hardhat_reset", [options] if options is not None else None
        )

    def set_coinbase(self, address: str) -> None:
        self._communicator.send_request("hardhat_setCoinbase", [address])

    def get_automine(self) -> bool:
        return self._communicator.send_request("hardhat_getAutomine")

    def set_automine(self, value: bool) -> None:
        self._communicator.send_request("evm_setAutomine", [value])

    def set_code(self, address: str, value: bytes) -> None:
        self._communicator.send_request(
            "hardhat_setCode", [address, "0x" + value.hex()]
        )

    def set_nonce(self, address: str, value: int) -> None:
        self._communicator.send_request("hardhat_setNonce", [address, hex(value)])

    def set_next_block_timestamp(self, timestamp: int) -> None:
        self._communicator.send_request("evm_setNextBlockTimestamp", [hex(timestamp)])

    def send_unsigned_transaction(self, params: TxParams) -> str:
        raise NotImplementedError(
            "Hardhat does not support sending unsigned transactions"
        )

    def set_next_block_base_fee_per_gas(self, value: int) -> None:
        self._communicator.send_request(
            "hardhat_setNextBlockBaseFeePerGas", [hex(value)]
        )

    def set_min_gas_price(self, value: int) -> None:
        self._communicator.send_request("hardhat_setMinGasPrice", [hex(value)])

    def set_storage_at(self, address: str, position: int, value: bytes) -> None:
        self._communicator.send_request(
            "hardhat_setStorageAt", [address, hex(position), "0x" + value.hex()]
        )

    def mine_many(self, num_blocks: int, timestamp_change: Optional[int]) -> None:
        self._communicator.send_request(
            "hardhat_mine",
            [hex(num_blocks), hex(timestamp_change)]
            if timestamp_change is not None
            else [hex(num_blocks)],
        )

    def hardhat_metadata(self) -> Dict[str, Any]:
        return self._communicator.send_request("hardhat_metadata")


class AnvilChainInterface(ChainInterfaceAbc):
    def get_accounts(self) -> List[str]:
        return self._communicator.send_request("eth_accounts")

    def set_balance(self, address: str, value: int) -> None:
        self._communicator.send_request("anvil_setBalance", [address, hex(value)])

    def impersonate_account(self, address: str) -> None:
        self._communicator.send_request("anvil_impersonateAccount", [address])

    def stop_impersonating_account(self, address: str) -> None:
        self._communicator.send_request("anvil_stopImpersonatingAccount", [address])

    def set_block_gas_limit(self, gas_limit: int) -> None:
        self._communicator.send_request("evm_setBlockGasLimit", [hex(gas_limit)])

    def reset(self, options: Optional[Dict] = None) -> None:
        self._communicator.send_request(
            "anvil_reset", [options] if options is not None else None
        )

    def set_coinbase(self, address: str) -> None:
        self._communicator.send_request("anvil_setCoinbase", [address])

    def get_automine(self) -> bool:
        return self._communicator.send_request("anvil_getAutomine")

    def set_automine(self, value: bool) -> None:
        self._communicator.send_request("evm_setAutomine", [value])

    def set_code(self, address: str, value: bytes) -> None:
        self._communicator.send_request("anvil_setCode", [address, "0x" + value.hex()])

    def set_nonce(self, address: str, value: int) -> None:
        self._communicator.send_request("anvil_setNonce", [address, hex(value)])

    def set_next_block_timestamp(self, timestamp: int) -> None:
        self._communicator.send_request("evm_setNextBlockTimestamp", [hex(timestamp)])

    def send_unsigned_transaction(self, params: TxParams) -> str:
        return self._communicator.send_request(
            "eth_sendUnsignedTransaction", [self._encode_tx_params(params)]
        )

    def set_next_block_base_fee_per_gas(self, value: int) -> None:
        self._communicator.send_request("anvil_setNextBlockBaseFeePerGas", [hex(value)])

    def set_min_gas_price(self, value: int) -> None:
        self._communicator.send_request("anvil_setMinGasPrice", [hex(value)])

    def set_storage_at(self, address: str, position: int, value: bytes) -> None:
        self._communicator.send_request(
            "anvil_setStorageAt", [address, hex(position), "0x" + value.hex()]
        )

    def node_info(self) -> Dict[str, Any]:
        return self._communicator.send_request("anvil_nodeInfo")

    def mine_many(self, num_blocks: int, timestamp_change: Optional[int]) -> None:
        self._communicator.send_request(
            "anvil_mine",
            [hex(num_blocks), hex(timestamp_change)]
            if timestamp_change is not None
            else [hex(num_blocks)],
        )


class GanacheChainInterface(ChainInterfaceAbc):
    def get_accounts(self) -> List[str]:
        return self._communicator.send_request("eth_accounts")

    def set_balance(self, address: str, value: int) -> None:
        self._communicator.send_request("evm_setAccountBalance", [address, hex(value)])

    def add_account(self, address: str, passphrase: str) -> bool:
        return self._communicator.send_request(
            "evm_addAccount", [address, passphrase]
        ) and self._communicator.send_request(
            "personal_unlockAccount", [address, passphrase, hex(0)]
        )

    def set_block_gas_limit(self, gas_limit: int) -> None:
        raise NotImplementedError("Ganache does not support setting block gas limit")

    def reset(self, options: Optional[Dict] = None) -> None:
        raise NotImplementedError("Ganache does not support resetting the chain")

    def set_coinbase(self, address: str) -> None:
        raise NotImplementedError("Ganache does not support setting coinbase")

    def get_automine(self) -> bool:
        raise NotImplementedError("Ganache does not support automine")

    def set_automine(self, value: bool) -> None:
        raise NotImplementedError("Ganache does not support automine")

    def set_code(self, address: str, value: bytes) -> None:
        self._communicator.send_request(
            "evm_setAccountCode", [address, "0x" + value.hex()]
        )

    def set_nonce(self, address: str, value: int) -> None:
        self._communicator.send_request("evm_setAccountNonce", [address, hex(value)])

    def set_next_block_timestamp(self, timestamp: int) -> None:
        raise NotImplementedError(
            "Ganache does not support setting next block timestamp"
        )

    def send_unsigned_transaction(self, params: TxParams) -> str:
        raise NotImplementedError(
            "Ganache does not support sending unsigned transactions"
        )

    def set_next_block_base_fee_per_gas(self, value: int) -> None:
        raise NotImplementedError(
            "Ganache does not support setting next block base fee per gas"
        )

    def set_min_gas_price(self, value: int) -> None:
        self._communicator.send_request("miner_setGasPrice", [hex(value)])

    def set_storage_at(self, address: str, position: int, value: bytes) -> None:
        self._communicator.send_request(
            "evm_setAccountStorageAt", [address, hex(position), "0x" + value.hex()]
        )

    def mine_many(self, num_blocks: int, timestamp_change: Optional[int]) -> None:
        if timestamp_change is not None:
            raise NotImplementedError(
                "Ganache does not support timestamp intervals when mining multiple blocks"
            )
        self._communicator.send_request(
            "evm_mine",
            [{"blocks": num_blocks}],
        )


class GethLikeChainInterfaceAbc(ChainInterfaceAbc, ABC):
    @property
    @abstractmethod
    def _name(self) -> str:
        ...

    def get_accounts(self) -> List[str]:
        return []

    def get_automine(self) -> bool:
        raise NotImplementedError(f"{self._name} does not support automine")

    def set_automine(self, value: bool) -> None:
        raise NotImplementedError(f"{self._name} does not support automine")

    def reset(self, options: Optional[Dict] = None) -> None:
        raise NotImplementedError(f"{self._name} does not support resetting the chain")

    def set_coinbase(self, address: str) -> None:
        raise NotImplementedError(f"{self._name} does not support setting coinbase")

    def set_balance(self, address: str, value: int) -> None:
        raise NotImplementedError(f"{self._name} does not support setting balance")

    def set_block_gas_limit(self, gas_limit: int) -> None:
        raise NotImplementedError(
            f"{self._name} does not support setting block gas limit"
        )

    def set_code(self, address: str, value: bytes) -> None:
        raise NotImplementedError(f"{self._name} does not support setting code")

    def set_nonce(self, address: str, value: int) -> None:
        raise NotImplementedError(f"{self._name} does not support setting nonce")

    def set_next_block_timestamp(self, timestamp: int) -> None:
        raise NotImplementedError(
            f"{self._name} does not support setting next block timestamp"
        )

    def send_unsigned_transaction(self, params: TxParams) -> str:
        raise NotImplementedError(
            f"{self._name} does not support sending unsigned transactions"
        )

    def set_next_block_base_fee_per_gas(self, value: int) -> None:
        raise NotImplementedError(
            f"{self._name} does not support setting next block base fee per gas"
        )

    def set_min_gas_price(self, value: int) -> None:
        raise NotImplementedError(
            f"{self._name} does not support setting min gas price"
        )

    def set_storage_at(self, address: str, position: int, value: bytes) -> None:
        raise NotImplementedError(f"{self._name} does not support setting storage")

    def mine_many(self, num_blocks: int, timestamp_change: Optional[int]) -> None:
        raise NotImplementedError(f"{self._name} does not support mining blocks")


class GethChainInterface(GethLikeChainInterfaceAbc):
    @property
    def _name(self) -> str:
        return "Geth"

    def get_accounts(self) -> List[str]:
        return self._communicator.send_request("eth_accounts")


class HermezChainInterface(GethLikeChainInterfaceAbc):
    @property
    def _name(self) -> str:
        return "Hermez"


class NitroChainInterface(GethLikeChainInterfaceAbc):
    @property
    def _name(self) -> str:
        return "Nitro"


class AvalancheChainInterface(GethLikeChainInterfaceAbc):
    @property
    def _name(self) -> str:
        return "Avalanche"


class ErigonChainInterface(GethLikeChainInterfaceAbc):
    @property
    def _name(self) -> str:
        return "Erigon"
