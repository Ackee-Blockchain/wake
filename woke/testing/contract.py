import dataclasses
import itertools
from contextlib import contextmanager
from enum import IntEnum
from typing import (
    Any,
    Dict,
    Iterable,
    List,
    Optional,
    Sequence,
    Tuple,
    Type,
    Union,
    get_type_hints,
)

import eth_abi
import eth_utils
import web3.contract
from eth_typing import HexStr
from hexbytes import HexBytes
from typing_extensions import Literal
from web3 import Web3
from web3._utils.abi import get_abi_input_types, get_abi_output_types
from web3._utils.empty import Empty
from web3.types import TxParams, TxReceipt

from woke.testing.abi_to_type import RequestType
from woke.testing.development_chains import (
    AnvilDevChain,
    DevChainABC,
    GanacheDevChain,
    HardhatDevChain,
)


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
        return super().__new__(cls, Web3.toChecksumAddress(addr))

    def __eq__(self, other):
        if not isinstance(other, str):
            return NotImplemented
        return Web3.toChecksumAddress(self) == Web3.toChecksumAddress(other)

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


class TransactionRevertedError(Exception):
    def __init__(self, name, data):
        super().__init__(f"{name}({', '.join(map(repr, data))})")


# global interface for communicating with the devchain
class DevchainInterface:
    __dev_chain: DevChainABC
    __port: int
    __w3: Web3
    __accounts: List[Address]
    __block_gas_limit: int
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

    def __init__(self, port: int):
        self.__port = port
        self.__w3 = Web3(
            Web3.WebsocketProvider(f"ws://127.0.0.1:{str(port)}", websocket_timeout=60)
        )
        # self.__w3 = Web3(Web3.IPCProvider(f"/tmp/anvil.ipc"))
        # self.__w3 = Web3(Web3.HTTPProvider(f"http://127.0.0.1:{str(port)}"))
        client_version: str = self.__w3.clientVersion.lower()
        print(f"client version: {client_version}")
        if "anvil" in client_version:
            self.__dev_chain = AnvilDevChain(self.__w3)
        elif "hardhat" in client_version:
            self.__dev_chain = HardhatDevChain(self.__w3)
        elif "ethereumjs" in client_version:
            self.__dev_chain = GanacheDevChain(self.__w3)
        else:
            raise NotImplementedError(f"Client version {client_version} not supported")
        self.__accounts = [Address(acc) for acc in self.__w3.eth.accounts]
        block_info = self.__w3.eth.get_block("latest")
        assert "gasLimit" in block_info
        self.__block_gas_limit = block_info["gasLimit"]
        if len(self.__accounts) > 0:
            self.__w3.eth.default_account = self.__accounts[0]

    @property
    def accounts(self) -> Tuple[Address, ...]:
        return tuple(self.__accounts)

    @property
    def default_account(self) -> Optional[Address]:
        default_acc = self.__w3.eth.default_account
        if isinstance(default_acc, Empty):
            return None
        return Address(default_acc)

    @default_account.setter
    def default_account(self, account: Union[Address, str]) -> None:
        self.__w3.eth.default_account = str(account)

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
            return value._contract.address
        elif isinstance(value, Address):
            return str(value)
        else:
            return value

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
        self.__accounts = [Address(acc) for acc in self.__w3.eth.accounts]

    def _process_revert_data(self, revert_data: bytes, errors: Dict[bytes, Any]):
        selector = revert_data[0:4]
        if selector not in errors:
            raise NotImplementedError(
                f"Transaction reverted with unknown error selector {selector.hex()}"
            )
        revert_data = eth_abi.abi.decode(
            get_abi_input_types(errors[selector]), revert_data[4:]
        )

        if selector == bytes.fromhex("4e487b71"):
            # panic
            assert len(revert_data) == 1
            code = int(revert_data[0])
            if code not in self.__panic_reasons:
                revert_data = (f"Unknown panic reason {code}",)
            else:
                revert_data = (self.__panic_reasons[code],)

        raise TransactionRevertedError(errors[selector]["name"], revert_data)

    def _process_tx_result(
        self,
        tx_params: TxParams,
        tx_hash: Union[HexBytes, HexStr],
        errors: Dict[bytes, Any],
    ) -> TxReceipt:
        print(tx_hash)
        tx_receipt = self.__w3.eth.wait_for_transaction_receipt(tx_hash)
        if tx_receipt["status"] == 0:
            if isinstance(self.__dev_chain, AnvilDevChain):
                # eth_call cannot be used because web3.py throws an exception without the revert reason data
                output = self.dev_chain.retrieve_transaction_data([], tx_hash)
                self._process_revert_data(bytes.fromhex(output), errors)
            elif isinstance(self.__dev_chain, GanacheDevChain):
                # should also revert
                try:
                    self.__w3.eth.call(tx_params)
                    raise AssertionError("Transaction should have reverted")
                except ValueError as e:
                    try:
                        revert_data = e.args[0]["data"][2:]
                    except Exception:
                        raise e
                self._process_revert_data(bytes.fromhex(revert_data), errors)
            elif isinstance(self.__dev_chain, HardhatDevChain):
                data = self.__w3.eth.call(tx_params)
                self._process_revert_data(data, errors)
        return tx_receipt

    def deploy(
        self,
        abi,
        bytecode,
        arguments: Iterable,
        params: TxParams,
        errors: Dict[bytes, Any],
    ) -> web3.contract.Contract:
        arguments = [self._convert_to_web3_type(arg) for arg in arguments]
        factory = self.__w3.eth.contract(abi=abi, bytecode=bytecode)

        if "from" not in params and self.default_account is None:
            raise ValueError("No from_ account specified and no default account set")

        with _signer_account(
            Address(params["from"]) if "from" in params else self.default_account, self
        ):
            try:
                tx_hash = factory.constructor(*arguments).transact(params)
            except ValueError as e:
                try:
                    tx_hash = e.args[0]["data"]["txHash"]
                except Exception:
                    raise e

        tx_receipt = self._process_tx_result(
            factory.constructor(*arguments).build_transaction(params), tx_hash, errors
        )

        return self.__w3.eth.contract(address=tx_receipt["contractAddress"], abi=abi)  # type: ignore

    def call(
        self,
        contract,
        selector: HexStr,
        arguments: Iterable,
        params: TxParams,
        return_type: Type,
    ) -> Any:
        arguments = [self._convert_to_web3_type(arg) for arg in arguments]
        func = contract.get_function_by_selector(selector)(*arguments)
        web3_data = func.call(params)
        return self._convert_from_web3_type(web3_data, return_type)

    def transact(
        self,
        contract: web3.contract.Contract,
        selector: HexStr,
        arguments: Iterable,
        params: TxParams,
        return_tx,
        request_type,
        return_type: Type,
        errors: Dict[bytes, Any],
    ) -> Any:
        arguments = [self._convert_to_web3_type(arg) for arg in arguments]
        func = contract.get_function_by_selector(selector)(*arguments)
        output_abi = get_abi_output_types(func.abi)

        if "from" not in params and self.default_account is None:
            raise ValueError("No from_ account specified and no default account set")

        with _signer_account(
            Address(params["from"]) if "from" in params else self.default_account, self
        ):
            try:
                tx_hash = func.transact(params)
            except ValueError as e:
                try:
                    tx_hash = e.args[0]["data"]["txHash"]
                except Exception:
                    raise e

        tx_receipt = self._process_tx_result(
            func.build_transaction(params), tx_hash, errors
        )
        output = self.dev_chain.retrieve_transaction_data([], tx_hash)

        web3_data = eth_abi.abi.decode(
            output_abi, bytes.fromhex(output)
        )  # pyright: reportGeneralTypeIssues=false
        return self._convert_from_web3_type(web3_data, return_type)

    def create_factory(self, addr: Union[Address, str], abi) -> web3.contract.Contract:
        contract = self.__w3.eth.contract(abi=abi, address=addr)
        assert isinstance(contract, web3.contract.Contract)
        return contract


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


dev_interface = DevchainInterface(8545)


class Contract:
    _abi: List
    _bytecode: HexStr
    _contract: web3.contract.Contract
    _errors: Dict[bytes, Any]

    def __init__(self, addr: Union[Address, str]):
        self._contract = dev_interface.create_factory(addr, self.__class__._abi)
        self._errors = {}

        # built-in Error(str) and Panic(uint256) errors
        error_abi = {
            "name": "Error",
            "type": "error",
            "inputs": [{"name": "message", "type": "string"}],
        }
        panic_abi = {
            "name": "Panic",
            "type": "error",
            "inputs": [{"name": "code", "type": "uint256"}],
        }

        for item in itertools.chain(self.__class__._abi, [error_abi, panic_abi]):
            if item["type"] == "error":
                selector = eth_utils.function_abi_to_4byte_selector(
                    item
                )  # pyright: reportPrivateImportUsage=false
                self._errors[selector] = item

    def __str__(self):
        return f"{self.__class__.__name__}({self._contract.address})"

    def __repr__(self):
        return self.__str__()

    @classmethod
    # TODO add option to deploy using a different instance of web3
    def _deploy(
        cls,
        arguments: Iterable,
        from_: Optional[Union[Address, str]],
        value: Wei,
        gas_limit: Union[int, Literal["max"], Literal["auto"]],
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

        errors = {}

        # built-in Error(str) and Panic(uint256) errors
        error_abi = {
            "name": "Error",
            "type": "error",
            "inputs": [{"name": "message", "type": "string"}],
        }
        panic_abi = {
            "name": "Panic",
            "type": "error",
            "inputs": [{"name": "code", "type": "uint256"}],
        }

        for item in itertools.chain(cls._abi, [error_abi, panic_abi]):
            if item["type"] == "error":
                selector = eth_utils.function_abi_to_4byte_selector(
                    item
                )  # pyright: reportPrivateImportUsage=false
                errors[selector] = item

        contract = dev_interface.deploy(
            cls._abi, cls._bytecode, arguments, params, errors
        )
        return cls(contract.address)

    def _transact(
        self,
        selector: HexStr,
        arguments: Iterable,
        return_tx: bool,
        request_type: RequestType,
        return_type: Type,
        from_: Optional[Union[Address, str]],
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
                to = to._contract.address
            params["to"] = to
        return dev_interface.transact(
            self._contract,
            selector,
            arguments,
            params,
            return_tx,
            request_type,
            return_type,
            self._errors,
        )

    def _call(
        self,
        selector: HexStr,
        arguments: Iterable,
        return_tx: bool,
        return_type: Type,
        from_: Optional[Union[Address, str]],
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
                to = to._contract.address
            params["to"] = to
        return dev_interface.call(
            self._contract, selector, arguments, params, return_type
        )
