from __future__ import annotations

import dataclasses
import functools
import importlib
import re
from collections import defaultdict
from contextlib import contextmanager
from enum import IntEnum
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    DefaultDict,
    Dict,
    Iterable,
    List,
    Optional,
    Set,
    Tuple,
    Type,
    Union,
    cast,
    get_type_hints,
    overload,
)

import eth_abi
import eth_utils
from Crypto.Hash import BLAKE2b
from typing_extensions import Literal, get_args, get_origin

from woke.testing.development_chains import (
    AnvilDevChain,
    DevChainABC,
    GanacheDevChain,
    HardhatDevChain,
)
from woke.testing.pytypes_generator import RequestType

from . import hardhat_console
from .internal import UnknownEvent, UnknownTransactionRevertedError
from .json_rpc.communicator import JsonRpcCommunicator, JsonRpcError, TxParams
from .utils import read_from_memory

if TYPE_CHECKING:
    from .transactions import LegacyTransaction


class Abi:
    @classmethod
    def encode(cls, types: Iterable, arguments: Iterable) -> bytes:
        return eth_abi.encode(  # pyright: ignore[reportPrivateImportUsage]
            types, arguments
        )

    @classmethod
    def decode(cls, types: Iterable, data: bytes) -> Any:
        return eth_abi.decode(types, data)  # pyright: ignore[reportPrivateImportUsage]


class Wei(int):
    def to_ether(self) -> float:
        return self / 10**18

    @classmethod
    def from_ether(cls, value: Union[int, float]) -> Wei:
        return cls(int(value * 10**18))


@functools.total_ordering
class Address:
    ZERO: Address

    def __init__(self, address: Union[str, int]) -> None:
        if isinstance(address, int):
            self._address = eth_utils.to_checksum_address(
                format(address, "#042x")
            )  # pyright: reportPrivateImportUsage=false
        else:
            self._address = eth_utils.to_checksum_address(
                address
            )  # pyright: reportPrivateImportUsage=false

    def __str__(self) -> str:
        return self._address

    def __repr__(self) -> str:
        return self._address

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, Address):
            return self._address == other._address
        elif isinstance(other, str):
            return self._address == eth_utils.to_checksum_address(
                other
            )  # pyright: reportPrivateImportUsage=false
        elif isinstance(other, Account):
            raise TypeError(
                "Cannot compare Address and Account. Use Account.address instead"
            )
        else:
            return NotImplemented

    def __lt__(self, other: Any) -> bool:
        if isinstance(other, Address):
            return int(self._address, 16) < int(other._address, 16)
        elif isinstance(other, str):
            return int(self._address, 16) < int(
                eth_utils.to_checksum_address(other), 16
            )
        elif isinstance(other, Account):
            raise TypeError(
                "Cannot compare Address and Account. Use Account.address instead"
            )
        else:
            return NotImplemented

    def __hash__(self) -> int:
        return hash(self._address)


Address.ZERO = Address(0)


class Account:
    _address: Address
    _chain: ChainInterface

    def __init__(
        self, address: Union[Address, str, int], chain: Optional[ChainInterface] = None
    ) -> None:
        if isinstance(address, Address):
            self._address = address
        else:
            self._address = Address(address)
        self._chain = chain if chain is not None else default_chain

    def __str__(self) -> str:
        return str(self._address)

    def __repr__(self) -> str:
        return str(self._address)

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, Account):
            return self._address == other._address and self._chain == other._chain
        elif isinstance(other, Address):
            raise TypeError(
                "Cannot compare Account to Address. Use Account.address == Address"
            )
        return NotImplemented

    def __hash__(self) -> int:
        return hash((self._address, self._chain))

    @property
    def address(self) -> Address:
        return self._address

    @property
    def balance(self) -> Wei:
        return Wei(self._chain.dev_chain.get_balance(str(self._address)))

    @balance.setter
    def balance(self, value: int) -> None:
        if not isinstance(value, int):
            raise TypeError("value must be an integer")
        if value < 0:
            raise ValueError("value must be non-negative")
        self._chain.dev_chain.set_balance(str(self.address), value)

    @property
    def code(self) -> bytes:
        return self._chain.dev_chain.get_code(str(self._address))

    @code.setter
    def code(self, value: Union[bytes, bytearray]) -> None:
        if not isinstance(value, (bytes, bytearray)):
            raise TypeError("value must be a bytes object")
        self._chain.dev_chain.set_code(str(self.address), value)

    @property
    def chain(self) -> ChainInterface:
        return self._chain

    @property
    def nonce(self) -> int:
        return self._chain.dev_chain.get_transaction_count(str(self._address))

    @nonce.setter
    def nonce(self, value: int) -> None:
        if not isinstance(value, int):
            raise TypeError("value must be an integer")
        if value < 0:
            raise ValueError("value must be non-negative")
        self._chain.dev_chain.set_nonce(str(self.address), value)

    def _prepare_tx_params(
        self,
        data: Union[bytes, bytearray] = b"",
        value: int = 0,
        from_: Optional[Union[Account, Address, str]] = None,
        gas_limit: Union[int, Literal["max"], Literal["auto"]] = "max",
    ):
        params: TxParams = {
            "type": 0,
            "value": value,
            "data": data,
            "gas_price": self._chain.gas_price,
            "to": str(self.address),
        }
        if from_ is None:
            if self._chain.default_account is None:
                raise ValueError("No from_ specified and no default account set")
            params["from"] = str(self._chain.default_account.address)
        elif isinstance(from_, Account):
            if from_.chain != self.chain:
                raise ValueError("`from_` account must belong to this chain")
            params["from"] = str(from_.address)
        else:
            params["from"] = str(from_)

        params["nonce"] = self._chain._get_nonce(params["from"])

        if gas_limit == "max":
            params["gas"] = self.chain.block_gas_limit
        elif gas_limit == "auto":
            params["gas"] = self.chain.dev_chain.estimate_gas(params)
        elif isinstance(gas_limit, int):
            params["gas"] = gas_limit
        else:
            raise ValueError("invalid gas limit")

        return params

    def call(
        self,
        data: Union[bytes, bytearray] = b"",
        value: int = 0,
        from_: Optional[Union[Account, Address, str]] = None,
        gas_limit: Union[int, Literal["max"], Literal["auto"]] = "max",
    ) -> bytearray:
        params = self._prepare_tx_params(data, value, from_, gas_limit)
        try:
            output = self._chain.dev_chain.call(params)
        except JsonRpcError as e:
            if isinstance(self._chain.dev_chain, AnvilDevChain) and e.data["code"] == 3:
                # call reverted, try to send as a transaction to get more info
                # TODO what if auto-mine is off?
                return self.transact(data, value, from_, gas_limit, False)
            elif (
                isinstance(self._chain.dev_chain, HardhatDevChain)
                and e.data["code"] == -32603
            ):
                # call reverted, try to send as a transaction to get more info
                # TODO what if auto-mine is off?
                return self.transact(data, value, from_, gas_limit, False)
            raise e from None

        return bytearray(output)

    @overload
    def transact(
        self,
        data: Union[bytes, bytearray] = b"",
        value: int = 0,
        from_: Optional[Union[Account, Address, str]] = None,
        gas_limit: Union[int, Literal["max"], Literal["auto"]] = "max",
        return_tx: Literal[False] = False,
    ) -> bytearray:
        ...

    @overload
    def transact(
        self,
        data: Union[bytes, bytearray] = b"",
        value: int = 0,
        from_: Optional[Union[Account, Address, str]] = None,
        gas_limit: Union[int, Literal["max"], Literal["auto"]] = "max",
        return_tx: Literal[True] = True,
    ) -> LegacyTransaction[bytearray]:
        ...

    def transact(
        self,
        data: Union[bytes, bytearray] = b"",
        value: int = 0,
        from_: Optional[Union[Account, Address, str]] = None,
        gas_limit: Union[int, Literal["max"], Literal["auto"]] = "max",
        return_tx: bool = False,
    ) -> Union[bytearray, LegacyTransaction[bytearray]]:
        tx_params = self._prepare_tx_params(data, value, from_, gas_limit)
        sender = Account(tx_params["from"], self._chain)

        with _signer_account(sender):
            try:
                tx_hash = self._chain.dev_chain.send_transaction(tx_params)
            except (ValueError, JsonRpcError) as e:
                try:
                    tx_hash = e.args[0]["data"]["txHash"]
                except Exception:
                    raise e
            self.chain._nonces[sender.address] += 1

        assert "to" in tx_params
        recipient_fqn = get_fqn_from_address(Address(tx_params["to"]), self.chain)

        from .transactions import LegacyTransaction

        tx = LegacyTransaction[bytearray](
            tx_hash,
            tx_params,
            None,
            bytearray,
            recipient_fqn,
            self.chain,
        )

        if return_tx:
            return tx

        tx.wait()

        if self._chain.console_logs_callback is not None:
            logs = tx.console_logs
            if len(logs) > 0:
                self._chain.console_logs_callback(tx, logs)

        if self._chain.events_callback is not None:
            events = tx.events
            if len(events) > 0:
                self._chain.events_callback(tx, events)

        return tx.return_value


class RevertToSnapshotFailedError(Exception):
    pass


class NotConnectedError(Exception):
    pass


class AlreadyConnectedError(Exception):
    pass


def _check_connected(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if not args[0].connected:
            raise NotConnectedError("Not connected to a chain")
        return f(*args, **kwargs)

    return wrapper


def get_fqn_from_deployment_code(deployment_code: bytes) -> str:
    for deployment_code_segments, fqn in deployment_code_index:

        length, h = deployment_code_segments[0]
        if length > len(deployment_code):
            continue
        segment_h = BLAKE2b.new(data=deployment_code[:length], digest_bits=256).digest()
        if segment_h != h:
            continue

        deployment_code = deployment_code[length:]
        found = True

        for length, h in deployment_code_segments[1:]:
            if length + 20 > len(deployment_code):
                found = False
                break
            deployment_code = deployment_code[20:]
            segment_h = BLAKE2b.new(
                data=deployment_code[:length], digest_bits=256
            ).digest()
            if segment_h != h:
                found = False
                break
            deployment_code = deployment_code[length:]

        if found:
            return fqn

    raise ValueError("Could not find contract definition from deployment code")


def get_fqn_from_address(addr: Address, chain: ChainInterface) -> Optional[str]:
    code = chain.dev_chain.get_code(str(addr))
    metadata = code[-53:]
    if metadata in contracts_by_metadata:
        return contracts_by_metadata[metadata]
    else:
        return None


class ChainInterface:
    _connected: bool
    _dev_chain: DevChainABC
    _accounts: List[Account]
    _default_account: Optional[Account]
    _block_gas_limit: int
    _gas_price: int
    _chain_id: int
    _nonces: DefaultDict[Address, int]
    _snapshots: Dict[str, Dict]
    _deployed_libraries: DefaultDict[bytes, List[Library]]
    _single_source_errors: Set[bytes]

    console_logs_callback: Optional[Callable[[LegacyTransaction, List[Any]], None]]
    events_callback: Optional[
        Callable[[LegacyTransaction, List[Tuple[bytes, Any]]], None]
    ]

    def __init__(self):
        self._connected = False

    @contextmanager
    def connect(self, uri: str):
        if self._connected:
            raise AlreadyConnectedError("Already connected to a chain")

        communicator = JsonRpcCommunicator(uri)
        try:
            communicator.__enter__()
            self._connected = True

            client_version = communicator.web3_client_version().lower()
            if "anvil" in client_version:
                self._dev_chain = AnvilDevChain(communicator)
            elif "hardhat" in client_version:
                self._dev_chain = HardhatDevChain(communicator)
            elif "ethereumjs" in client_version:
                self._dev_chain = GanacheDevChain(communicator)
            else:
                raise NotImplementedError(
                    f"Client version {client_version} not supported"
                )
            self._accounts = [Account(acc, self) for acc in self._dev_chain.accounts()]
            block_info = self._dev_chain.get_block("latest")
            assert "gasLimit" in block_info
            self._block_gas_limit = int(block_info["gasLimit"], 16)
            self._chain_id = self._dev_chain.get_chain_id()
            self._gas_price = self._dev_chain.get_gas_price()
            self._nonces = defaultdict(lambda: 0)
            self._snapshots = {}
            self._deployed_libraries = defaultdict(list)
            self._default_account = None

            self._single_source_errors = {
                selector
                for selector, sources in errors.items()
                if len({source for fqn, source in sources.items()}) == 1
            }

            self.console_logs_callback = None
            self.events_callback = None

            yield
        finally:
            if communicator.connected:
                communicator.__exit__(None, None, None)
            self._connected = False

    @contextmanager
    def change_automine(self, automine: bool):
        if not self._connected:
            raise NotConnectedError("Not connected to a chain")
        automine_was = self._dev_chain.get_automine()
        self._dev_chain.set_automine(automine)
        try:
            yield
        finally:
            self._dev_chain.set_automine(automine_was)

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    @_check_connected
    def chain_id(self) -> int:
        return self._chain_id

    @property
    @_check_connected
    def automine(self) -> bool:
        return self._dev_chain.get_automine()

    @automine.setter
    @_check_connected
    def automine(self, value: bool) -> None:
        self._dev_chain.set_automine(value)

    @property
    @_check_connected
    def accounts(self) -> Tuple[Account, ...]:
        return tuple(self._accounts)

    @property
    @_check_connected
    def default_account(self) -> Optional[Account]:
        return self._default_account

    @default_account.setter
    @_check_connected
    def default_account(self, account: Union[Account, Address, str]) -> None:
        if isinstance(account, Account):
            self._default_account = account
        else:
            self._default_account = Account(account, self)

    @property
    @_check_connected
    def block_gas_limit(self) -> int:
        return self._block_gas_limit

    @block_gas_limit.setter
    @_check_connected
    def block_gas_limit(self, value: int) -> None:
        self._dev_chain.set_block_gas_limit(value)
        self._block_gas_limit = value

    @property
    @_check_connected
    def gas_price(self) -> int:
        return self._gas_price

    @gas_price.setter
    @_check_connected
    def gas_price(self, value: int) -> None:
        self._gas_price = value

    @property
    @_check_connected
    def dev_chain(self):
        return self._dev_chain

    @_check_connected
    def mine(self, timestamp_change: Optional[Callable[[int], int]] = None) -> None:
        if timestamp_change is not None:
            block_info = self._dev_chain.get_block("latest")
            assert "timestamp" in block_info
            last_timestamp = int(block_info["timestamp"], 16)
            timestamp = timestamp_change(last_timestamp)
        else:
            timestamp = None

        self._dev_chain.mine(timestamp)

    def _convert_to_web3_type(self, value: Any) -> Any:
        if dataclasses.is_dataclass(value):
            return tuple(
                self._convert_to_web3_type(v) for v in dataclasses.astuple(value)
            )
        elif isinstance(value, list):
            return [self._convert_to_web3_type(v) for v in value]
        elif isinstance(value, tuple):
            return tuple(self._convert_to_web3_type(v) for v in value)
        elif isinstance(value, Account):
            if value.chain != self:
                raise ValueError("Account must belong to this chain")
            return str(value.address)
        elif isinstance(value, Address):
            return str(value)
        else:
            return value

    def _parse_console_log_data(self, data: bytes):
        selector = data[:4]

        if selector not in hardhat_console.abis:
            raise ValueError(f"Unknown selector: {selector.hex()}")
        abi = hardhat_console.abis[selector]

        output_types = [
            eth_utils.abi.collapse_if_tuple(cast(Dict[str, Any], arg)) for arg in abi
        ]
        decoded_data = list(
            eth_abi.abi.decode(output_types, data[4:])
        )  # pyright: reportGeneralTypeIssues=false
        for i in range(len(decoded_data)):
            if abi[i]["type"] == "address":
                decoded_data[i] = Account(decoded_data[i], self)

        if len(decoded_data) == 1:
            decoded_data = decoded_data[0]

        return decoded_data

    def _convert_from_web3_type(self, value: Any, expected_type: Type) -> Any:
        if isinstance(expected_type, type(None)):
            return None
        elif get_origin(expected_type) is list:
            return [
                self._convert_from_web3_type(v, get_args(expected_type)[0])
                for v in value
            ]
        elif dataclasses.is_dataclass(expected_type):
            assert isinstance(value, tuple)
            resolved_types = get_type_hints(expected_type)
            field_types = [
                resolved_types[field.name]
                for field in dataclasses.fields(expected_type)
            ]
            assert len(value) == len(field_types)
            converted_values = [
                self._convert_from_web3_type(v, t) for v, t in zip(value, field_types)
            ]
            return expected_type(*converted_values)
        elif isinstance(expected_type, type):
            if issubclass(expected_type, Contract):
                return expected_type(value, self)
            elif issubclass(expected_type, Account):
                return Account(value, self)
            elif issubclass(expected_type, Address):
                return expected_type(value)
            elif issubclass(expected_type, IntEnum):
                return expected_type(value)
        return value

    @_check_connected
    def update_accounts(self):
        self._accounts = [Account(acc, self) for acc in self._dev_chain.accounts()]

    @_check_connected
    def snapshot(self) -> str:
        snapshot_id = self._dev_chain.snapshot()

        self._snapshots[snapshot_id] = {
            "nonces": self._nonces.copy(),
            "accounts": self._accounts.copy(),
            "default_account": self._default_account,
            "block_gas_limit": self._block_gas_limit,
        }
        return snapshot_id

    @_check_connected
    def revert(self, snapshot_id: str) -> None:
        reverted = self._dev_chain.revert(snapshot_id)
        if not reverted:
            raise RevertToSnapshotFailedError()

        snapshot = self._snapshots[snapshot_id]
        self._nonces = snapshot["nonces"]
        self._accounts = snapshot["accounts"]
        self._default_account = snapshot["default_account"]
        self._block_gas_limit = snapshot["block_gas_limit"]
        del self._snapshots[snapshot_id]

    @property
    @_check_connected
    def deployed_libraries(self) -> DefaultDict[bytes, List[Library]]:
        return self._deployed_libraries

    @contextmanager
    def snapshot_and_revert(self):
        snapshot_id = self.snapshot()
        try:
            yield
        finally:
            self.revert(snapshot_id)

    @_check_connected
    def reset(self) -> None:
        self._dev_chain.reset()

    def _get_nonce(self, address: Union[str, Address]) -> int:
        if address not in self._nonces:
            self._nonces[address] = self._dev_chain.get_transaction_count(str(address))
        return self._nonces[address]

    def _build_transaction(
        self, params: Dict, data: bytes, arguments: Iterable, abi: Optional[Dict]
    ) -> TxParams:
        if abi is None:
            data += Abi.encode([], [])
        else:
            arguments = [self._convert_to_web3_type(arg) for arg in arguments]
            types = [
                eth_utils.abi.collapse_if_tuple(cast(Dict[str, Any], arg))
                for arg in abi["inputs"]
            ]
            data += Abi.encode(types, arguments)

        if "from" in params:
            sender = params["from"]
        elif self.default_account is not None:
            sender = self.default_account.address
        else:
            raise ValueError("No from_ account specified and no default account set")

        if "gas" in params:
            gas = params["gas"]
        else:
            # auto
            estimate_params = {
                "from": str(sender),
                "value": params["value"] if "value" in params else 0,
                "data": data,
                "gas_price": self._gas_price,
            }
            if "to" in params:
                estimate_params["to"] = params["to"]
            gas = self._dev_chain.estimate_gas(estimate_params)

        tx: TxParams = {
            "type": 0,
            "nonce": self._get_nonce(sender),
            "from": str(sender),
            "gas": gas,
            "value": params["value"] if "value" in params else 0,
            "data": data,
            "gas_price": self._gas_price,
            # "max_priority_fee_per_gas": 0,
            # "max_fee_per_gas": 0,
            # "access_list": [],
            # "chain_id": self.__chain_id
        }
        if "to" in params:
            tx["to"] = params["to"]
        return tx

    def _process_revert_data(
        self, tx_hash, revert_data: bytes, origin: Union[Address, str]
    ):
        selector = revert_data[0:4]
        if selector not in errors:
            raise UnknownTransactionRevertedError(revert_data)

        if selector not in self._single_source_errors:
            # ambiguous error, try to find the source contract
            debug_trace = self._dev_chain.debug_trace_transaction(
                tx_hash, {"enableMemory": True}
            )
            try:
                fqn = self._process_debug_trace_for_revert(debug_trace, origin)
            except ValueError:
                raise UnknownTransactionRevertedError(revert_data)
        else:
            fqn = list(errors[selector].keys())[0]

        module_name, attrs = errors[selector][fqn]
        obj = getattr(importlib.import_module(module_name), attrs[0])
        for attr in attrs[1:]:
            obj = getattr(obj, attr)
        abi = obj._abi

        types = [
            eth_utils.abi.collapse_if_tuple(cast(Dict[str, Any], arg))
            for arg in abi["inputs"]
        ]
        decoded = Abi.decode(types, revert_data[4:])
        generated_error = self._convert_from_web3_type(decoded, obj)
        # raise native pytypes exception on transaction revert
        raise generated_error

    def _process_events(
        self, tx_hash: str, logs: List, origin: Union[Address, str]
    ) -> list:
        if len(logs) == 0:
            return []

        generated_events = []

        non_unique = False
        for log in logs:
            if len(log["topics"]) == 0:
                continue

            selector = log["topics"][0]
            if selector.startswith("0x"):
                selector = selector[2:]
            selector = bytes.fromhex(selector)

            if selector not in events:
                continue

            if len(events[selector]) > 1:
                non_unique = True
                break

        if non_unique:
            debug_trace = self._dev_chain.debug_trace_transaction(
                tx_hash, {"enableMemory": True}
            )
            event_traces = self._process_debug_trace_for_events(debug_trace, origin)
            assert len(event_traces) == len(logs)
        else:
            event_traces = [(None, None)] * len(logs)

        for log, (traced_selector, fqn) in zip(logs, event_traces):
            topics = [
                bytes.fromhex(t[2:]) if t.startswith("0x") else bytes.fromhex(t)
                for t in log["topics"]
            ]
            data = (
                bytes.fromhex(log["data"][2:])
                if log["data"].startswith("0x")
                else bytes.fromhex(log["data"])
            )

            if len(topics) == 0:
                generated_events.append(UnknownEvent([], data))
                continue

            selector = topics[0]

            if selector not in events:
                generated_events.append(UnknownEvent(topics, data))
                continue

            if len(events[selector]) > 1:
                assert traced_selector == selector

                if fqn is None:
                    generated_events.append(UnknownEvent(topics, data))
                    continue

                found = False
                for base_fqn in contracts_inheritance[fqn]:
                    if base_fqn in events[selector]:
                        found = True
                        fqn = base_fqn
                        break

                if not found:
                    generated_events.append(UnknownEvent(topics, data))
                    continue
            else:
                fqn = list(events[selector].keys())[0]

            module_name, attrs = events[selector][fqn]
            obj = getattr(importlib.import_module(module_name), attrs[0])
            for attr in attrs[1:]:
                obj = getattr(obj, attr)
            abi = obj._abi

            topic_index = 1
            types = []

            decoded_indexed = []

            for input in abi["inputs"]:
                if input["indexed"]:
                    if (
                        input["type"] in {"string", "bytes"}
                        or input["internalType"].startswith("struct ")
                        or input["type"].endswith("]")
                    ):
                        topic_type = "bytes32"
                    else:
                        topic_type = input["type"]
                    topic_data = log["topics"][topic_index]
                    decoded_indexed.append(
                        Abi.decode([topic_type], bytes.fromhex(topic_data[2:]))[0]
                    )
                    topic_index += 1
                else:
                    types.append(eth_utils.abi.collapse_if_tuple(input))
            decoded = list(Abi.decode(types, bytes.fromhex(log["data"][2:])))
            merged = []

            for input in abi["inputs"]:
                if input["indexed"]:
                    merged.append(decoded_indexed.pop(0))
                else:
                    merged.append(decoded.pop(0))

            merged = tuple(merged)
            generated_event = self._convert_from_web3_type(merged, obj)
            generated_events.append(generated_event)

        return generated_events

    def _process_tx_receipt(
        self,
        tx_receipt: Dict[str, Any],
        tx_hash: str,
        tx_params: TxParams,
        origin: Union[Address, str],
    ) -> None:
        if int(tx_receipt["status"], 16) == 0:
            if isinstance(self._dev_chain, (AnvilDevChain, GanacheDevChain)):
                # should also revert
                try:
                    self._dev_chain.call(tx_params)
                    raise AssertionError("Transaction should have reverted")
                except JsonRpcError as e:
                    try:
                        revert_data = e.data["data"][2:]
                    except Exception:
                        raise e
                self._process_revert_data(tx_hash, bytes.fromhex(revert_data), origin)
            elif isinstance(self._dev_chain, HardhatDevChain):
                try:
                    _ = self._dev_chain.call(tx_params)
                    raise AssertionError("Transaction should have reverted")
                except JsonRpcError as e:
                    data = bytes.fromhex(e.data["data"]["data"][2:])
                self._process_revert_data(tx_hash, data, origin)

    def _process_return_data(self, output: bytes, abi: Dict, return_type: Type):
        output_types = [
            eth_utils.abi.collapse_if_tuple(cast(Dict[str, Any], arg))
            for arg in abi["outputs"]
        ]
        decoded_data = eth_abi.abi.decode(
            output_types, output
        )  # pyright: reportGeneralTypeIssues=false
        if isinstance(decoded_data, (list, tuple)) and len(decoded_data) == 1:
            decoded_data = decoded_data[0]
        return self._convert_from_web3_type(decoded_data, return_type)

    def _process_console_logs(self, trace_output: List[Dict[str, Any]]) -> List:
        hardhat_console_address = bytes.fromhex(
            "000000000000000000636F6e736F6c652e6c6f67"
        )
        console_logs = []
        for trace in trace_output:
            if "action" in trace and "to" in trace["action"]:
                if bytes.fromhex(trace["action"]["to"][2:]) == hardhat_console_address:
                    console_logs.append(
                        self._parse_console_log_data(
                            bytes.fromhex(trace["action"]["input"][2:])
                        )
                    )
        return console_logs

    @_check_connected
    def deploy(
        self,
        abi: Dict[Union[bytes, Literal["constructor"]], Any],
        deployment_code: bytes,
        arguments: Iterable,
        params: TxParams,
        return_tx: bool,
        return_type: Type,
    ) -> Any:
        tx_params = self._build_transaction(
            params,
            deployment_code,
            arguments,
            abi["constructor"] if "constructor" in abi else None,
        )
        sender = (
            Account(params["from"], self) if "from" in params else self.default_account
        )
        if sender is None:
            raise ValueError("No from_ account specified and no default account set")

        with _signer_account(sender):
            try:
                tx_hash = self._dev_chain.send_transaction(tx_params)
            except ValueError as e:
                try:
                    tx_hash = e.args[0]["data"]["txHash"]
                except Exception:
                    raise e
            self._nonces[sender.address] += 1

        deployed_contract_fqn = get_fqn_from_deployment_code(deployment_code)

        from .transactions import LegacyTransaction

        tx = LegacyTransaction[return_type](
            tx_hash,
            tx_params,
            abi["constructor"] if "constructor" in abi else None,
            return_type,
            deployed_contract_fqn,
            self,
        )

        if return_tx:
            return tx

        tx.wait()

        if self.console_logs_callback is not None:
            logs = tx.console_logs
            if len(logs) > 0:
                self.console_logs_callback(tx, logs)

        if self.events_callback is not None:
            events = tx.events
            if len(events) > 0:
                self.events_callback(tx, events)

        return tx.return_value

    @_check_connected
    def call(
        self,
        selector: bytes,
        abi: Dict[Union[bytes, Literal["constructor"]], Any],
        arguments: Iterable,
        params: TxParams,
        return_type: Type,
    ) -> Any:
        tx_params = self._build_transaction(params, selector, arguments, abi[selector])
        try:
            output = self._dev_chain.call(tx_params)
        except JsonRpcError as e:
            if isinstance(self._dev_chain, AnvilDevChain) and e.data["code"] == 3:
                # call reverted, try to send as a transaction to get more info
                # TODO what if auto-mine is off?
                return self.transact(
                    selector, abi, arguments, params, False, return_type
                )
            elif (
                isinstance(self._dev_chain, HardhatDevChain)
                and e.data["code"] == -32603
            ):
                # call reverted, try to send as a transaction to get more info
                # TODO what if auto-mine is off?
                return self.transact(
                    selector, abi, arguments, params, False, return_type
                )
            raise e from None
        return self._process_return_data(output, abi[selector], return_type)

    def _process_debug_trace_for_events(
        self, debug_trace: Dict, origin: Union[Address, str]
    ) -> List[Tuple[bytes, Optional[str]]]:
        addresses = [origin]
        event_fqns = []

        for trace in debug_trace["structLogs"]:
            if trace["op"] in {"CALL", "CALLCODE", "DELEGATECALL", "STATICCALL"}:
                addr = int(trace["stack"][-2], 16)
                addresses.append(Address(addr))
            elif trace["op"] in {"CREATE", "CREATE2"}:
                offset = int(trace["stack"][-2], 16)
                length = int(trace["stack"][-3], 16)

                deployment_code = read_from_memory(offset, length, trace["memory"])
                fqn = get_fqn_from_deployment_code(deployment_code)
                addresses.append(fqn)
            elif trace["op"] in {"RETURN", "REVERT", "STOP"}:
                addresses.pop()
            elif trace["op"] in {"LOG1", "LOG2", "LOG3", "LOG4"}:
                selector = trace["stack"][-3]
                if selector.startswith("0x"):
                    selector = selector[2:]
                selector = bytes.fromhex(selector)

                if not isinstance(addresses[-1], str):
                    if addresses[-1] == "0x000000000000000000636F6e736F6c652e6c6f67":
                        # skip events from console.log
                        event_fqns.append((selector, None))
                        continue

                    address_fqn = get_fqn_from_address(addresses[-1], self)
                    if address_fqn is None:
                        raise ValueError(
                            f"Could not find contract with address {addresses[-1]}"
                        )
                    event_fqns.append((selector, address_fqn))
                else:
                    event_fqns.append((selector, addresses[-1]))

        return event_fqns

    def _process_debug_trace_for_revert(
        self, debug_trace: Dict, origin: Union[Address, str]
    ) -> str:
        addresses = [origin]
        last_revert_origin = None

        for trace in debug_trace["structLogs"]:
            if trace["op"] in {"CALL", "CALLCODE", "DELEGATECALL", "STATICCALL"}:
                addr = int(trace["stack"][-2], 16)
                addresses.append(Address(addr))
            elif trace["op"] in {"CREATE", "CREATE2"}:
                offset = int(trace["stack"][-2], 16)
                length = int(trace["stack"][-3], 16)

                deployment_code = read_from_memory(offset, length, trace["memory"])
                fqn = get_fqn_from_deployment_code(deployment_code)
                addresses.append(fqn)
            elif trace["op"] == "REVERT":
                addr = addresses.pop()
                pc = trace["pc"]
                if isinstance(addr, str):
                    fqn = addr
                else:
                    fqn = get_fqn_from_address(addr, self)

                if fqn in contracts_revert_index and pc in contracts_revert_index[fqn]:
                    last_revert_origin = fqn
            elif trace["op"] in {"RETURN", "STOP"}:
                addresses.pop()

        if last_revert_origin is None:
            raise ValueError("Could not find revert origin")
        return last_revert_origin

    @_check_connected
    def transact(
        self,
        selector: bytes,
        abi: Dict[Union[bytes, Literal["constructor"]], Any],
        arguments: Iterable,
        params: TxParams,
        return_tx: bool,
        return_type: Type,
    ) -> Any:
        tx_params = self._build_transaction(params, selector, arguments, abi[selector])
        sender = (
            Account(params["from"], self) if "from" in params else self.default_account
        )
        if sender is None:
            raise ValueError("No from_ account specified and no default account set")

        with _signer_account(sender):
            try:
                tx_hash = self._dev_chain.send_transaction(tx_params)
            except (ValueError, JsonRpcError) as e:
                try:
                    tx_hash = e.args[0]["data"]["txHash"]
                except Exception:
                    raise e
            self._nonces[sender.address] += 1

        assert "to" in tx_params
        recipient_fqn = get_fqn_from_address(Address(tx_params["to"]), self)

        from .transactions import LegacyTransaction

        tx = LegacyTransaction[return_type](
            tx_hash,
            tx_params,
            abi[selector],
            return_type,
            recipient_fqn,
            self,
        )

        if return_tx:
            return tx

        tx.wait()

        if self.console_logs_callback is not None:
            logs = tx.console_logs
            if len(logs) > 0:
                self.console_logs_callback(tx, logs)

        if self.events_callback is not None:
            events = tx.events
            if len(events) > 0:
                self.events_callback(tx, events)

        return tx.return_value


@contextmanager
def _signer_account(sender: Account):
    chain = sender.chain
    dev_chain = chain.dev_chain
    account_created = True
    if sender not in chain.accounts:
        chain.update_accounts()
        if sender not in chain.accounts:
            account_created = False

    if not account_created:
        if isinstance(dev_chain, (AnvilDevChain, HardhatDevChain)):
            dev_chain.impersonate_account(str(sender))
        elif isinstance(dev_chain, GanacheDevChain):
            dev_chain.add_account(str(sender), "")
        else:
            raise NotImplementedError()

    try:
        yield
    finally:
        if not account_created and isinstance(
            dev_chain, (AnvilDevChain, HardhatDevChain)
        ):
            dev_chain.stop_impersonating_account(str(sender))


default_chain = ChainInterface()
# selector => (contract_fqn => pytypes_object)
errors: Dict[bytes, Dict[str, Any]] = {}
# selector => (contract_fqn => pytypes_object)
events: Dict[bytes, Dict[str, Any]] = {}
# contract_fqn => contract type
contracts_by_fqn: Dict[str, Any] = {}
# contract_metadata => contract_fqn
contracts_by_metadata: Dict[bytes, str] = {}
# contract_fqn => tuple of linearized base contract fqns
contracts_inheritance: Dict[str, Tuple[str, ...]] = {}
# contract_fqn => set of REVERT opcode PCs belonging to a revert statement
contracts_revert_index: Dict[str, Set[int]] = {}
# list of pairs of (deployment code segments, contract_fqn)
# where deployment code segments is a tuple of (length, BLAKE2b hash)
deployment_code_index: List[Tuple[Tuple[Tuple[int, bytes], ...], str]] = []

contract_internal_jumps_in: Dict[str, Set[int]] = {}
contract_internal_jumps_out: Dict[str, Set[int]] = {}
contract_internal_jumpdests: Dict[str, Dict[int, Tuple[Optional[str], str]]] = {}

LIBRARY_PLACEHOLDER_REGEX = re.compile(r"__\$[0-9a-fA-F]{34}\$__")


def get_contracts_by_fqn() -> Dict[str, Any]:
    return contracts_by_fqn


def get_contract_internal_jumps_in() -> Dict[str, Set[int]]:
    return contract_internal_jumps_in


def get_contract_internal_jumps_out() -> Dict[str, Set[int]]:
    return contract_internal_jumps_out


def get_contract_internal_jumpdests() -> Dict[str, Dict[int, Tuple[str, str]]]:
    return contract_internal_jumpdests


class Contract(Account):
    _abi: Dict[
        Union[bytes, Literal["constructor"], Literal["fallback"], Literal["receive"]],
        Any,
    ]
    _deployment_code: str

    def __init__(
        self, addr: Union[Account, Address, str], chain: ChainInterface = default_chain
    ):
        if isinstance(addr, Account):
            if addr.chain != chain:
                raise ValueError("Account and chain must be from the same chain")
            addr = addr.address
        super().__init__(addr, chain)

    def __str__(self):
        return f"{self.__class__.__name__}({self._address})"

    def __repr__(self):
        return self.__str__()

    @classmethod
    def _get_deployment_code(
        cls, libraries: Dict[bytes, Tuple[Union[Account, Address], str]]
    ) -> bytes:
        deployment_code = cls._deployment_code
        for match in LIBRARY_PLACEHOLDER_REGEX.finditer(deployment_code):
            lib_id = bytes.fromhex(match.group(0)[3:-3])
            assert (
                lib_id in libraries
            ), f"Address of library {libraries[lib_id][1]} required to generate deployment code"

            lib = libraries[lib_id][0]
            if isinstance(lib, Account):
                lib_addr = str(lib.address)[2:]
            elif isinstance(lib, Address):
                lib_addr = str(lib)[2:]
            else:
                raise TypeError()

            deployment_code = (
                deployment_code[: match.start()]
                + lib_addr
                + deployment_code[match.end() :]
            )
        return bytes.fromhex(deployment_code)

    @classmethod
    def _deploy(
        cls,
        arguments: Iterable,
        return_tx: bool,
        return_type: Type,
        from_: Optional[Union[Account, Address, str]],
        value: int,
        gas_limit: Union[int, Literal["max"], Literal["auto"]],
        libraries: Dict[bytes, Tuple[Union[Account, Address, None], str]],
        chain: Optional[ChainInterface],
    ) -> Any:
        params = {}
        if chain is None:
            chain = default_chain

        if from_ is not None:
            if isinstance(from_, Account):
                if from_.chain != chain:
                    raise ValueError("from_ account must belong to the chain")
                params["from"] = str(from_.address)
            else:
                params["from"] = str(from_)
        params["value"] = value

        if gas_limit == "max":
            params["gas"] = chain.block_gas_limit
        elif gas_limit == "auto":
            pass
        elif isinstance(gas_limit, int):
            params["gas"] = gas_limit
        else:
            raise ValueError("invalid gas limit")

        deployment_code = cls._deployment_code
        for match in LIBRARY_PLACEHOLDER_REGEX.finditer(deployment_code):
            lib_id = bytes.fromhex(match.group(0)[3:-3])
            assert lib_id in libraries

            lib = libraries[lib_id][0]
            if lib is not None:
                if isinstance(lib, Account):
                    lib_addr = str(lib.address)[2:]
                else:
                    lib_addr = str(lib)[2:]
            elif lib_id in chain.deployed_libraries:
                lib_addr = str(chain.deployed_libraries[lib_id][-1].address)[2:]
            else:
                raise ValueError(f"Library {libraries[lib_id][1]} not deployed")

            deployment_code = (
                deployment_code[: match.start()]
                + lib_addr
                + deployment_code[match.end() :]
            )

        return chain.deploy(
            cls._abi,
            bytes.fromhex(deployment_code),
            arguments,
            params,
            return_tx,
            return_type,
        )

    def _transact(
        self,
        selector: str,
        arguments: Iterable,
        return_tx: bool,
        request_type: RequestType,
        return_type: Type,
        from_: Optional[Union[Account, Address, str]],
        to: Optional[Union[Account, Address, str]],
        value: int,
        gas_limit: Union[int, Literal["max"], Literal["auto"]],
    ) -> Any:
        params = {}
        if from_ is not None:
            if isinstance(from_, Account):
                if from_.chain != self.chain:
                    raise ValueError("`from_` account must belong to this chain")
                params["from"] = str(from_.address)
            else:
                params["from"] = str(from_)
        params["value"] = value

        if gas_limit == "max":
            params["gas"] = self.chain.block_gas_limit
        elif gas_limit == "auto":
            pass
        elif isinstance(gas_limit, int):
            params["gas"] = gas_limit
        else:
            raise ValueError("invalid gas limit")

        if to is not None:
            if isinstance(to, Account):
                if to.chain != self.chain:
                    raise ValueError("`to` account must belong to this chain")
                params["to"] = str(to.address)
            else:
                params["to"] = str(to)
        else:
            params["to"] = str(self._address)

        return self.chain.transact(
            bytes.fromhex(selector),
            self.__class__._abi,
            arguments,
            params,
            return_tx,
            return_type,
        )

    def _call(
        self,
        selector: str,
        arguments: Iterable,
        return_tx: bool,
        return_type: Type,
        from_: Optional[Union[Account, Address, str]],
        to: Optional[Union[Account, Address, str]],
        value: int,
        gas_limit: Union[int, Literal["max"], Literal["auto"]],
    ) -> Any:
        if return_tx:
            raise ValueError("transaction can't be returned from a call")
        params = {}
        if from_ is not None:
            if isinstance(from_, Account):
                if from_.chain != self.chain:
                    raise ValueError("`from_` account must belong to this chain")
                params["from"] = str(from_.address)
            else:
                params["from"] = str(from_)
        params["value"] = value

        if gas_limit == "max":
            params["gas"] = self.chain.block_gas_limit
        elif gas_limit == "auto":
            pass
        elif isinstance(gas_limit, int):
            params["gas"] = gas_limit
        else:
            raise ValueError("invalid gas limit")

        if to is not None:
            if isinstance(to, Account):
                if to.chain != self.chain:
                    raise ValueError("`to` account must belong to this chain")
                params["to"] = str(to.address)
            else:
                params["to"] = str(to)
        else:
            params["to"] = str(self._address)

        sel = bytes.fromhex(selector)
        return self.chain.call(sel, self.__class__._abi, arguments, params, return_type)


class Library(Contract):
    _library_id: bytes

    @classmethod
    def _deploy(
        cls,
        arguments: Iterable,
        return_tx: bool,
        return_type: Type,
        from_: Optional[Union[Account, Address, str]],
        value: int,
        gas_limit: Union[int, Literal["max"], Literal["auto"]],
        libraries: Dict[bytes, Tuple[Union[Account, Address, None], str]],
        chain: Optional[ChainInterface],
    ) -> Any:
        if chain is None:
            chain = default_chain

        lib = super()._deploy(
            arguments, return_tx, return_type, from_, value, gas_limit, libraries, chain
        )
        chain.deployed_libraries[cls._library_id].append(lib)
        return lib
