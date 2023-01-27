import enum
import json
import logging
import platform
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from typing_extensions import TypedDict

from woke.config import WokeConfig

from .abc import ProtocolAbc
from .http import HttpProtocol
from .ipc import IpcProtocol
from .websocket import WebsocketProtocol

logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)


class BlockEnum(str, enum.Enum):
    EARLIEST = "earliest"
    FINALIZED = "finalized"
    SAFE = "safe"
    LATEST = "latest"
    PENDING = "pending"


TxParams = TypedDict(
    "TxParams",
    {
        "type": int,
        "nonce": int,
        "to": str,
        "from": str,
        "gas": int,
        "value": int,
        "data": bytes,
        "gas_price": int,
        "max_priority_fee_per_gas": int,
        "max_fee_per_gas": int,
        "access_list": List,
        "chain_id": int,
    },
    total=False,
)


class JsonRpcError(Exception):
    def __init__(self, data: Dict):
        self.data = data


class JsonRpcCommunicator:
    _protocol: ProtocolAbc
    _request_id: int
    _connected: bool

    def __init__(self, config: WokeConfig, uri: str):
        if uri.startswith(("http://", "https://")):
            self._protocol = HttpProtocol(uri, config.testing.timeout)
        elif uri.startswith("ws://"):
            self._protocol = WebsocketProtocol(uri, config.testing.timeout)
        elif Path(uri).is_socket() or platform.system() == "Windows":
            self._protocol = IpcProtocol(uri, config.testing.timeout)
        else:
            raise ValueError(f"Invalid URI: {uri}")

        self._request_id = 0
        self._connected = False

    def __enter__(self):
        self._protocol.__enter__()
        self._connected = True
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self._protocol.__exit__(exc_type, exc_value, traceback)
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    def _send_request(self, method_name: str, params: Optional[List] = None) -> Any:
        post_data = {
            "jsonrpc": "2.0",
            "method": method_name,
            "params": params if params is not None else [],
            "id": self._request_id,
        }
        logger.info(f"Sending request:\n{post_data}")
        self._request_id += 1

        response = self._protocol.send_recv(json.dumps(post_data))
        logger.info(f"Received response:\n{json.dumps(response)}")
        return response

    @staticmethod
    def _process_response(response: Any) -> Any:
        if "error" in response:
            raise JsonRpcError(response["error"])
        return response["result"]

    @staticmethod
    def _encode_transaction(transaction: TxParams) -> Dict:
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
            tx["gas"] = hex(transaction["gas"])
        if "value" in transaction:
            tx["value"] = hex(transaction["value"])
        if "data" in transaction:
            tx["data"] = "0x" + transaction["data"].hex()
        if "gas_price" in transaction:
            tx["gasPrice"] = hex(transaction["gas_price"])
        if "max_priority_fee_per_gas" in transaction:
            tx["maxPriorityFeePerGas"] = hex(transaction["max_priority_fee_per_gas"])
        if "max_fee_per_gas" in transaction:
            tx["maxFeePerGas"] = hex(transaction["max_fee_per_gas"])
        if "access_list" in transaction:
            tx["accessList"] = transaction["access_list"]
        if "chain_id" in transaction:
            tx["chainId"] = hex(transaction["chain_id"])
        return tx

    def eth_get_block_by_number(
        self, block: Union[int, str], include_transactions: bool
    ) -> Dict:
        """Returns information about a block by block number."""
        if isinstance(block, int):
            params = [hex(block), include_transactions]
        elif isinstance(block, str):
            params = [block, include_transactions]
        else:
            raise TypeError("block must be either int or BlockEnum")
        text = self._send_request("eth_getBlockByNumber", params)
        return self._process_response(text)

    def eth_get_transaction_by_hash(self, tx_hash: str) -> Dict:
        """Returns the information about a transaction requested by transaction hash."""
        text = self._send_request("eth_getTransactionByHash", [tx_hash])
        return self._process_response(text)

    def eth_block_number(self) -> int:
        """Returns the number of most recent block."""
        text = self._send_request("eth_blockNumber")
        return int(self._process_response(text), 16)

    def eth_chain_id(self) -> int:
        """Returns the chain ID of the current network."""
        text = self._send_request("eth_chainId")
        return int(self._process_response(text), 16)

    def eth_accounts(self) -> List[str]:
        """Returns a list of addresses owned by client."""
        text = self._send_request("eth_accounts")
        return self._process_response(text)

    def eth_coinbase(self) -> str:
        """Returns the coinbase address."""
        text = self._send_request("eth_coinbase")
        return self._process_response(text)

    def eth_get_code(
        self, address: str, block: Union[int, str] = BlockEnum.LATEST
    ) -> bytes:
        """Returns code at a given address."""
        params = [address]
        if isinstance(block, int):
            params.append(hex(block))
        elif isinstance(block, str):
            params.append(block)
        else:
            raise TypeError("block must be either int or BlockEnum")
        text = self._send_request("eth_getCode", params)
        return bytes.fromhex(self._process_response(text)[2:])

    def eth_call(
        self,
        transaction: TxParams,
        block: Union[int, str] = BlockEnum.LATEST,
    ) -> bytes:
        """Executes a new message call immediately without creating a transaction on the block chain."""
        params: List[Any] = [self._encode_transaction(transaction)]
        if isinstance(block, int):
            params.append(hex(block))
        elif isinstance(block, str):
            params.append(block)
        else:
            raise TypeError("block must be either int or BlockEnum")
        text = self._send_request("eth_call", params)
        return bytes.fromhex(self._process_response(text)[2:])

    def eth_estimate_gas(
        self, transaction: TxParams, block: Union[int, str] = BlockEnum.LATEST
    ) -> int:
        """Generates and returns an estimate of how much gas is necessary to allow the transaction to complete."""
        params: List[Any] = [self._encode_transaction(transaction)]
        if isinstance(block, int):
            params.append(hex(block))
        elif isinstance(block, str):
            params.append(block)
        else:
            raise TypeError("block must be either int or BlockEnum")
        text = self._send_request("eth_estimateGas", params)
        return int(self._process_response(text), 16)

    def eth_gas_price(self) -> int:
        """Returns the current price per gas in wei."""
        text = self._send_request("eth_gasPrice")
        return int(self._process_response(text), 16)

    def eth_get_balance(
        self, address: str, block: Union[int, str] = BlockEnum.LATEST
    ) -> int:
        """Returns the balance of the account of given address."""
        params = [address]
        if isinstance(block, int):
            params.append(hex(block))
        elif isinstance(block, str):
            params.append(block)
        else:
            raise TypeError("block must be either int or BlockEnum")
        text = self._send_request("eth_getBalance", params)
        return int(self._process_response(text), 16)

    def eth_get_transaction_count(
        self, address: str, block: Union[int, str] = BlockEnum.LATEST
    ) -> int:
        """Returns the number of transactions sent from an address."""
        params = [address]
        if isinstance(block, int):
            params.append(hex(block))
        elif isinstance(block, str):
            params.append(block)
        else:
            raise TypeError("block must be either int or BlockEnum")
        text = self._send_request("eth_getTransactionCount", params)
        return int(self._process_response(text), 16)

    def eth_send_transaction(self, transaction: TxParams) -> str:
        """Signs and submits a transaction."""
        text = self._send_request(
            "eth_sendTransaction", [self._encode_transaction(transaction)]
        )
        return self._process_response(text)

    def eth_get_transaction_receipt(self, tx_hash: str) -> Optional[Dict]:
        """Returns the receipt of a transaction by transaction hash."""
        text = self._send_request("eth_getTransactionReceipt", [tx_hash])
        return self._process_response(text)

    def hardhat_set_balance(self, address: str, balance: int) -> None:
        """Sets the balance of the account of given address."""
        params = [address, hex(balance)]
        text = self._send_request("hardhat_setBalance", params)
        _ = self._process_response(text)

    def hardhat_set_coinbase(self, address: str) -> None:
        """Sets the coinbase address."""
        params = [address]
        text = self._send_request("hardhat_setCoinbase", params)
        _ = self._process_response(text)

    def hardhat_impersonate_account(self, address: str) -> None:
        """Impersonates an account."""
        params = [address]
        text = self._send_request("hardhat_impersonateAccount", params)
        _ = self._process_response(text)

    def hardhat_stop_impersonating_account(self, address: str) -> None:
        """Stops impersonating an account."""
        params = [address]
        text = self._send_request("hardhat_stopImpersonatingAccount", params)
        _ = self._process_response(text)

    def hardhat_reset(self, options: Optional[Dict] = None) -> None:
        text = self._send_request(
            "hardhat_reset", [options] if options is not None else []
        )
        _ = self._process_response(text)

    def hardhat_get_automine(self) -> bool:
        text = self._send_request("hardhat_getAutomine")
        return self._process_response(text)

    def hardhat_set_code(self, address: str, code: bytes) -> None:
        """Sets the code of the account of given address."""
        params = [address, "0x" + code.hex()]
        text = self._send_request("hardhat_setCode", params)
        _ = self._process_response(text)

    def hardhat_set_nonce(self, address: str, nonce: int) -> None:
        """Sets the nonce of the account of given address."""
        params = [address, hex(nonce)]
        text = self._send_request("hardhat_setNonce", params)
        _ = self._process_response(text)

    def anvil_set_balance(self, address: str, balance: int) -> None:
        params = [address, hex(balance)]
        text = self._send_request("anvil_setBalance", params)
        _ = self._process_response(text)

    def anvil_set_coinbase(self, address: str) -> None:
        params = [address]
        text = self._send_request("anvil_setCoinbase", params)
        _ = self._process_response(text)

    def anvil_impersonate_account(self, address: str) -> None:
        params = [address]
        text = self._send_request("anvil_impersonateAccount", params)
        _ = self._process_response(text)

    def anvil_stop_impersonating_account(self, address: str) -> None:
        params = [address]
        text = self._send_request("anvil_stopImpersonatingAccount", params)
        _ = self._process_response(text)

    def anvil_reset(self, options: Optional[Dict] = None) -> None:
        text = self._send_request(
            "anvil_reset", [options] if options is not None else []
        )
        _ = self._process_response(text)

    def anvil_get_automine(self) -> bool:
        text = self._send_request("anvil_getAutomine")
        return self._process_response(text)

    def anvil_set_code(self, address: str, code: bytes) -> None:
        params = [address, "0x" + code.hex()]
        text = self._send_request("anvil_setCode", params)
        _ = self._process_response(text)

    def anvil_set_nonce(self, address: str, nonce: int) -> None:
        params = [address, hex(nonce)]
        text = self._send_request("anvil_setNonce", params)
        _ = self._process_response(text)

    def evm_set_account_balance(self, address: str, balance: int) -> None:
        """Sets the given account's balance to the specified WEI value. Mines a new block before returning."""
        params = [address, hex(balance)]
        text = self._send_request("evm_setAccountBalance", params)
        _ = self._process_response(text)

    def evm_set_block_gas_limit(self, gas_limit: int) -> None:
        params = [hex(gas_limit)]
        text = self._send_request("evm_setBlockGasLimit", params)
        _ = self._process_response(text)

    def evm_add_account(self, address: str, passphrase: str) -> bool:
        params = [address, passphrase]
        text = self._send_request("evm_addAccount", params)
        return self._process_response(text)

    def evm_snapshot(self) -> str:
        text = self._send_request("evm_snapshot")
        return self._process_response(text)

    def evm_revert(self, snapshot_id: str) -> bool:
        text = self._send_request("evm_revert", [snapshot_id])
        return self._process_response(text)

    def evm_set_automine(self, automine: bool) -> None:
        text = self._send_request("evm_setAutomine", [automine])
        _ = self._process_response(text)

    def evm_mine(self, timestamp: Optional[int]) -> None:
        if timestamp is None:
            text = self._send_request("evm_mine")
        else:
            text = self._send_request("evm_mine", [hex(timestamp)])
        _ = self._process_response(text)

    def evm_set_next_block_timestamp(self, timestamp: int) -> None:
        text = self._send_request("evm_setNextBlockTimestamp", [hex(timestamp)])
        _ = self._process_response(text)

    def evm_set_account_code(self, address: str, code: bytes) -> None:
        params = [address, "0x" + code.hex()]
        text = self._send_request("evm_setAccountCode", params)
        _ = self._process_response(text)

    def evm_set_account_nonce(self, address: str, nonce: int) -> None:
        params = [address, hex(nonce)]
        text = self._send_request("evm_setAccountNonce", params)
        _ = self._process_response(text)

    def web3_client_version(self) -> str:
        """Returns the current client version."""
        text = self._send_request("web3_clientVersion")
        return self._process_response(text)

    def debug_trace_transaction(
        self, tx_hash: str, options: Optional[Dict] = None
    ) -> Dict:
        """Get debug traces of already-minted transactions."""
        params: List[Any] = [tx_hash]
        if options is not None:
            params.append(options)
        text = self._send_request("debug_traceTransaction", params)
        return self._process_response(text)

    def trace_transaction(self, tx_hash: str) -> List:
        text = self._send_request("trace_transaction", [tx_hash])
        return self._process_response(text)

    def personal_unlock_account(
        self, address: str, passphrase: str, duration: int
    ) -> bool:
        params = [address, passphrase, hex(duration)]
        text = self._send_request("personal_unlockAccount", params)
        return self._process_response(text)
