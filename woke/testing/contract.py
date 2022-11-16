import asyncio
import dataclasses
import re
from collections import defaultdict
from contextlib import contextmanager
from enum import IntEnum
from typing import (
    Any,
    Callable,
    DefaultDict,
    Dict,
    Iterable,
    List,
    Optional,
    Sequence,
    Tuple,
    Type,
    Union,
    cast,
    get_type_hints,
)

import aiohttp
import eth_abi
import eth_utils
from typing_extensions import Literal

from woke.testing.abi_to_type import RequestType
from woke.testing.development_chains import (
    AnvilDevChain,
    DevChainABC,
    GanacheDevChain,
    HardhatDevChain,
)

from . import hardhat_console
from .json_rpc.communicator import JsonRpcCommunicator, JsonRpcError, TxParams


class TransactionObject:
    pass


class Abi:
    @classmethod
    def encode(cls, arguments: Iterable, types: Iterable) -> bytes:
        return eth_abi.encode(  # pyright: ignore[reportPrivateImportUsage]
            types, arguments
        )

    @classmethod
    def decode(cls, data: bytes, types: Iterable) -> Any:
        return eth_abi.decode(types, data)  # pyright: ignore[reportPrivateImportUsage]


class Wei(int):
    def to_ether(self) -> float:
        return self / 10**18

    @classmethod
    def from_ether(cls, value: Union[int, float]) -> "Wei":
        return cls(int(value * 10**18))


class Address(str):
    def __new__(cls, addr):
        # cannot use isinstance(addr, Contract) because of circular dependency
        try:
            addr = addr._address
        except AttributeError:
            pass
        return super().__new__(
            cls, eth_utils.to_checksum_address(addr)
        )  # pyright: reportPrivateImportUsage=false

    def __eq__(self, other):
        if not isinstance(other, str):
            return NotImplemented
        return eth_utils.to_checksum_address(self) == eth_utils.to_checksum_address(
            other
        )  # pyright: reportPrivateImportUsage=false

    def __hash__(self):
        return hash(str(self))

    @property
    def balance(self) -> Wei:
        return Wei(dev_interface.dev_chain.get_balance(self))

    @balance.setter
    def balance(self, value: Union[Wei, int]) -> None:
        if not isinstance(value, int):
            raise TypeError("value must be an integer")
        if value < 0:
            raise ValueError("value must be non-negative")
        dev_interface.dev_chain.set_balance(self, value)


Address.ZERO = Address("0x0000000000000000000000000000000000000000")


class TransactionRevertedError(Exception):
    pass


class RevertToSnapshotFailedError(Exception):
    pass


# global interface for communicating with the devchain
class DevchainInterface:
    __dev_chain: DevChainABC
    __accounts: List[Address]
    __default_account: Optional[Address]
    __block_gas_limit: int
    __chain_id: int
    __nonces: DefaultDict[Address, int]
    __snapshots: Dict[str, Dict]
    __deployed_libraries: DefaultDict[bytes, List[Address]]
    __panic_reasons: Dict[int, str] = {
        0x00: "Generic compiler panic",
        0x01: "Assert evaluated to false",
        0x11: "Underflow or overflow",
        0x12: "Division or modulo by zero",
        0x21: "Too big or negative value converted to enum",
        0x22: "Access to incorrectly encoded storage byte array",
        0x31: ".pop() on empty array",
        0x32: "Out-of-bounds or negative index access to fixed-length array",
        0x41: "Too much memory allocated",
        0x51: "Called invalid internal function",
    }

    console_logs_callback: Optional[Callable[[str, List[Any]], None]]

    @contextmanager
    def connect(self, uri: str):
        loop = asyncio.get_event_loop()
        session = aiohttp.ClientSession()
        try:
            communicator = JsonRpcCommunicator(uri, session)
            client_version = loop.run_until_complete(
                communicator.web3_client_version()
            ).lower()
            if "anvil" in client_version:
                self.__dev_chain = AnvilDevChain(loop, communicator)
            elif "hardhat" in client_version:
                self.__dev_chain = HardhatDevChain(loop, communicator)
            elif "ethereumjs" in client_version:
                self.__dev_chain = GanacheDevChain(loop, communicator)
            else:
                raise NotImplementedError(
                    f"Client version {client_version} not supported"
                )
            self.__accounts = [Address(acc) for acc in self.__dev_chain.accounts()]
            block_info = self.__dev_chain.get_block("latest")
            assert "gasLimit" in block_info
            self.__block_gas_limit = int(block_info["gasLimit"], 16)
            self.__chain_id = self.__dev_chain.get_chain_id()
            self.__nonces = defaultdict(lambda: 0)
            self.__snapshots = {}
            self.__deployed_libraries = defaultdict(list)
            if len(self.__accounts) > 0:
                self.__default_account = self.__accounts[0]
            else:
                self.__default_account = None

            self.console_logs_callback = None

            yield
        finally:
            loop.run_until_complete(session.close())

    @property
    def accounts(self) -> Tuple[Address, ...]:
        return tuple(self.__accounts)

    @property
    def default_account(self) -> Optional[Address]:
        return self.__default_account

    @default_account.setter
    def default_account(self, account: Union[Address, str]) -> None:
        self.__default_account = Address(account)

    @property
    def block_gas_limit(self) -> int:
        return self.__block_gas_limit

    @block_gas_limit.setter
    def block_gas_limit(self, value: int) -> None:
        self.__dev_chain.set_block_gas_limit(value)
        self.__block_gas_limit = value

    @property
    def dev_chain(self):
        return self.__dev_chain

    @classmethod
    def _convert_to_web3_type(cls, value: Any) -> Any:
        if dataclasses.is_dataclass(value):
            return tuple(
                cls._convert_to_web3_type(v) for v in dataclasses.astuple(value)
            )
        elif isinstance(value, list):
            return [cls._convert_to_web3_type(v) for v in value]
        elif isinstance(value, tuple):
            return tuple(cls._convert_to_web3_type(v) for v in value)
        elif isinstance(value, Contract):
            return value._address
        elif isinstance(value, Address):
            return str(value)
        else:
            return value

    @classmethod
    def _parse_console_log_data(cls, data: bytes):
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
                decoded_data[i] = Address(decoded_data[i])

        if len(decoded_data) == 1:
            decoded_data = decoded_data[0]

        return decoded_data

    @classmethod
    def _convert_from_web3_type(cls, value: Any, expected_type: Type) -> Any:
        if isinstance(expected_type, type(None)):
            return None
        elif dataclasses.is_dataclass(expected_type):
            assert isinstance(value, tuple)
            resolved_types = get_type_hints(expected_type)
            field_types = [
                resolved_types[field.name]
                for field in dataclasses.fields(expected_type)
            ]
            assert len(value) == len(field_types)
            converted_values = [
                cls._convert_from_web3_type(v, t) for v, t in zip(value, field_types)
            ]
            return expected_type(*converted_values)
        elif isinstance(expected_type, type):
            if issubclass(expected_type, Contract):
                return expected_type(value)
            elif isinstance(expected_type, Address):
                return expected_type(value)
            elif issubclass(expected_type, IntEnum):
                return expected_type(value)
        return value

    def update_accounts(self):
        self.__accounts = [Address(acc) for acc in self.__dev_chain.accounts()]

    def snapshot(self) -> str:
        snapshot_id = self.__dev_chain.snapshot()

        self.__snapshots[snapshot_id] = {
            "nonces": self.__nonces.copy(),
            "accounts": self.__accounts.copy(),
            "default_account": self.__default_account,
            "block_gas_limit": self.__block_gas_limit,
        }
        return snapshot_id

    def revert(self, snapshot_id: str) -> None:
        reverted = self.__dev_chain.revert(snapshot_id)
        if not reverted:
            raise RevertToSnapshotFailedError()

        snapshot = self.__snapshots[snapshot_id]
        self.__nonces = snapshot["nonces"]
        self.__accounts = snapshot["accounts"]
        self.__default_account = snapshot["default_account"]
        self.__block_gas_limit = snapshot["block_gas_limit"]
        del self.__snapshots[snapshot_id]

    @property
    def deployed_libraries(self) -> DefaultDict[bytes, List[Address]]:
        return self.__deployed_libraries

    @contextmanager
    def snapshot_and_revert(self):
        snapshot_id = self.snapshot()
        try:
            yield
        finally:
            self.revert(snapshot_id)

    def reset(self) -> None:
        self.__dev_chain.reset()

    def _get_nonce(self, address: Address) -> int:
        if address not in self.__nonces:
            self.__nonces[address] = self.__dev_chain.get_transaction_count(
                str(address)
            )
        return self.__nonces[address]

    def _build_transaction(
        self, params: Dict, data: bytes, arguments: Iterable, abi: Optional[Dict]
    ) -> TxParams:
        if abi is None:
            data += eth_abi.encode([], [])
        else:
            arguments = [self._convert_to_web3_type(arg) for arg in arguments]
            types = [
                eth_utils.abi.collapse_if_tuple(cast(Dict[str, Any], arg))
                for arg in abi["inputs"]
            ]
            data += eth_abi.encode(types, arguments)

        if "from" in params:
            sender = params["from"]
        elif self.default_account is not None:
            sender = self.default_account
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
            }
            if "gas_price" in params:
                estimate_params["gas_price"] = params["gas_price"]
            if "to" in params:
                estimate_params["to"] = params["to"]
            gas = self.__dev_chain.estimate_gas(estimate_params)

        tx: TxParams = {
            "type": 2,
            "nonce": self._get_nonce(sender),
            "from": str(sender),
            "gas": gas,
            "value": params["value"] if "value" in params else 0,
            "data": data,
            # "gas_price": 0,
            # "max_priority_fee_per_gas": 0,
            # "max_fee_per_gas": 0,
            # "access_list": [],
            # "chain_id": self.__chain_id
        }
        if "to" in params:
            tx["to"] = params["to"]
        return tx

    def _process_revert_data(self, revert_data: bytes):
        selector = revert_data[0:4]
        if selector not in errors:
            raise NotImplementedError(
                f"Transaction reverted with unknown error selector {selector.hex()}"
            )
        if errors[selector]["type"] != "error":
            raise ValueError(f"Expected error abi, got {errors[selector]['type']}")

        types = [
            eth_utils.abi.collapse_if_tuple(cast(Dict[str, Any], arg))
            for arg in errors[selector]["inputs"]
        ]
        revert_data = eth_abi.abi.decode(types, revert_data[4:])

        if selector == bytes.fromhex("4e487b71"):
            # panic
            assert len(revert_data) == 1
            code = int(revert_data[0])
            if code not in self.__panic_reasons:
                revert_data = (f"Unknown panic reason {code}",)
            else:
                revert_data = (self.__panic_reasons[code],)

        exception_msg = (
            f"{errors[selector]['name']}({', '.join(map(repr, revert_data))})"
        )
        raise TransactionRevertedError(exception_msg)

    def _process_tx_result(
        self,
        tx_params: TxParams,
        tx_hash: str,
    ) -> Dict:
        tx_receipt = self.__dev_chain.wait_for_transaction_receipt(tx_hash)
        if int(tx_receipt["status"], 16) == 0:
            if isinstance(self.__dev_chain, (AnvilDevChain, GanacheDevChain)):
                # should also revert
                try:
                    self.__dev_chain.call(tx_params)
                    raise AssertionError("Transaction should have reverted")
                except JsonRpcError as e:
                    try:
                        revert_data = e.data["data"][2:]
                    except Exception:
                        raise e
                self._process_revert_data(bytes.fromhex(revert_data))
            elif isinstance(self.__dev_chain, HardhatDevChain):
                data = self.__dev_chain.call(tx_params)
                self._process_revert_data(data)
        return tx_receipt

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

    def deploy(
        self,
        abi: Dict[Union[bytes, Literal["constructor"]], Any],
        bytecode: bytes,
        arguments: Iterable,
        params: TxParams,
    ) -> Address:
        tx = self._build_transaction(
            params,
            bytecode,
            arguments,
            abi["constructor"] if "constructor" in abi else None,
        )
        sender = Address(params["from"]) if "from" in params else self.default_account

        with _signer_account(sender, self):
            try:
                tx_hash = self.__dev_chain.send_transaction(tx)
            except ValueError as e:
                try:
                    tx_hash = e.args[0]["data"]["txHash"]
                except Exception:
                    raise e

        tx_receipt = self._process_tx_result(tx, tx_hash)
        self.__nonces[sender] += 1
        assert (
            "contractAddress" in tx_receipt
            and tx_receipt["contractAddress"] is not None
        )
        return Address(tx_receipt["contractAddress"])

    def call(
        self,
        selector: bytes,
        abi: Dict[Union[bytes, Literal["constructor"]], Any],
        arguments: Iterable,
        params: TxParams,
        return_type: Type,
    ) -> Any:
        tx = self._build_transaction(params, selector, arguments, abi[selector])
        output = self.__dev_chain.call(tx)
        return self._process_return_data(output, abi[selector], return_type)

    def transact(
        self,
        selector: bytes,
        abi: Dict[Union[bytes, Literal["constructor"]], Any],
        arguments: Iterable,
        params: TxParams,
        return_tx,
        request_type,
        return_type: Type,
    ) -> Any:
        tx = self._build_transaction(params, selector, arguments, abi[selector])
        sender = Address(params["from"]) if "from" in params else self.default_account

        with _signer_account(sender, self):
            try:
                tx_hash = self.__dev_chain.send_transaction(tx)
            except ValueError as e:
                try:
                    tx_hash = e.args[0]["data"]["txHash"]
                except Exception:
                    raise e

        tx_receipt = self._process_tx_result(tx, tx_hash)
        self.__nonces[sender] += 1

        if isinstance(self.__dev_chain, AnvilDevChain):
            output = self.__dev_chain.trace_transaction(tx_hash)
            hardhat_console_address = bytes.fromhex(
                "000000000000000000636F6e736F6c652e6c6f67"
            )
            if self.console_logs_callback is not None:
                console_logs = []
                for trace in output:
                    if "action" in trace and "to" in trace["action"]:
                        if (
                            bytes.fromhex(trace["action"]["to"][2:])
                            == hardhat_console_address
                        ):
                            console_logs.append(
                                self._parse_console_log_data(
                                    bytes.fromhex(trace["action"]["input"][2:])
                                )
                            )

                if len(console_logs) > 0:
                    self.console_logs_callback(tx_hash, console_logs)

            output = bytes.fromhex(output[0]["result"]["output"][2:])
        elif isinstance(self.__dev_chain, (GanacheDevChain, HardhatDevChain)):
            output = self.__dev_chain.debug_trace_transaction(tx_hash)
            output = bytes.fromhex(output["returnValue"])
        else:
            raise NotImplementedError()

        return self._process_return_data(output, abi[selector], return_type)


@contextmanager
def _signer_account(address: Address, interface: DevchainInterface):
    chain = interface.dev_chain
    account_created = True
    if address not in interface.accounts:
        interface.update_accounts()
        if address not in interface.accounts:
            account_created = False

    if not account_created:
        if isinstance(chain, (AnvilDevChain, HardhatDevChain)):
            chain.impersonate_account(address)
        elif isinstance(chain, GanacheDevChain):
            chain.add_account(address, "")
        else:
            raise NotImplementedError()

    try:
        yield
    finally:
        if not account_created and isinstance(chain, (AnvilDevChain, HardhatDevChain)):
            chain.stop_impersonating_account(address)


dev_interface = DevchainInterface()
errors = {}
events = {}

LIBRARY_PLACEHOLDER_REGEX = re.compile(r"__\$[0-9a-fA-F]{34}\$__")


class Contract:
    _abi: Dict[Union[bytes, Literal["constructor"]], Any]
    _bytecode: str
    _address: Address

    def __init__(self, addr: Union[Address, str]):
        self._address = Address(addr)

    def __str__(self):
        return f"{self.__class__.__name__}({self._address})"

    def __repr__(self):
        return self.__str__()

    @classmethod
    # TODO add option to deploy using a different instance of web3
    def _deploy(
        cls,
        arguments: Iterable,
        from_: Optional[Union[Address, str, "Contract"]],
        value: Wei,
        gas_limit: Union[int, Literal["max"], Literal["auto"]],
        libraries: Dict[bytes, Tuple[Union["Contract", Address, None], str]],
    ) -> "Contract":
        params = {}
        if from_ is not None:
            params["from"] = Address(from_)
        params["value"] = value

        if gas_limit == "max":
            params["gas"] = dev_interface.block_gas_limit
        elif gas_limit == "auto":
            pass
        elif isinstance(gas_limit, int):
            params["gas"] = gas_limit
        else:
            raise ValueError("invalid gas limit")

        bytecode = cls._bytecode
        for match in LIBRARY_PLACEHOLDER_REGEX.finditer(bytecode):
            lib_id = bytes.fromhex(match.group(0)[3:-3])
            assert lib_id in libraries

            if libraries[lib_id][0] is not None:
                lib_addr = str(Address(libraries[lib_id][0]))[2:]
            elif lib_id in dev_interface.deployed_libraries:
                lib_addr = str(dev_interface.deployed_libraries[lib_id][-1])[2:]
            else:
                raise ValueError(f"Library {libraries[lib_id][1]} not deployed")

            bytecode = bytecode[: match.start()] + lib_addr + bytecode[match.end() :]

        address = dev_interface.deploy(
            cls._abi, bytes.fromhex(bytecode), arguments, params
        )
        return cls(address)

    def _transact(
        self,
        selector: str,
        arguments: Iterable,
        return_tx: bool,
        request_type: RequestType,
        return_type: Type,
        from_: Optional[Union[Address, str, "Contract"]],
        to: Optional[Union[Address, str, "Contract"]],
        value: Wei,
        gas_limit: Union[int, Literal["max"], Literal["auto"]],
    ) -> Any:
        if return_tx:
            raise NotImplementedError("returning a transaction is not implemented")
        params = {}
        if from_ is not None:
            params["from"] = Address(from_)
        params["value"] = value

        if gas_limit == "max":
            params["gas"] = dev_interface.block_gas_limit
        elif gas_limit == "auto":
            pass
        elif isinstance(gas_limit, int):
            params["gas"] = gas_limit
        else:
            raise ValueError("invalid gas limit")

        if to is not None:
            if isinstance(to, Contract):
                to = to._address
            params["to"] = to
        else:
            params["to"] = self._address

        return dev_interface.transact(
            bytes.fromhex(selector),
            self.__class__._abi,
            arguments,
            params,
            return_tx,
            request_type,
            return_type,
        )

    def _call(
        self,
        selector: str,
        arguments: Iterable,
        return_tx: bool,
        return_type: Type,
        from_: Optional[Union[Address, str, "Contract"]],
        to: Optional[Union[Address, str, "Contract"]],
        value: Wei,
        gas_limit: Union[int, Literal["max"], Literal["auto"]],
    ) -> Any:
        if return_tx:
            raise ValueError("transaction can't be returned from a call")
        params = {}
        if from_ is not None:
            params["from"] = Address(from_)
        params["value"] = value

        if gas_limit == "max":
            params["gas"] = dev_interface.block_gas_limit
        elif gas_limit == "auto":
            pass
        elif isinstance(gas_limit, int):
            params["gas"] = gas_limit
        else:
            raise ValueError("invalid gas limit")

        if to is not None:
            if isinstance(to, Contract):
                to = to._address
            params["to"] = to
        else:
            params["to"] = self._address

        sel = bytes.fromhex(selector)
        return dev_interface.call(
            sel, self.__class__._abi, arguments, params, return_type
        )


class Library(Contract):
    _library_id: bytes

    @classmethod
    def _deploy(
        cls,
        arguments: Iterable,
        from_: Optional[Union[Address, str, "Contract"]],
        value: Wei,
        gas_limit: Union[int, Literal["max"], Literal["auto"]],
        libraries: Dict[bytes, Tuple[Union["Contract", Address, None], str]],
    ) -> "Contract":
        ret = super()._deploy(arguments, from_, value, gas_limit, libraries)
        dev_interface.deployed_libraries[cls._library_id].append(Address(ret))
        return ret
