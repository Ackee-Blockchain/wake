import dataclasses
from contextlib import contextmanager
from enum import IntEnum
from typing import (
    Any,
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
import web3._utils.empty
import web3.contract
from eth_typing import HexStr
from web3 import Web3
from web3._utils.abi import get_abi_output_types
from web3._utils.empty import Empty
from web3.types import TxParams

from woke.fuzzer.abi_to_type import RequestType
from woke.fuzzer.development_chains import (
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


# global interface for communicating with the devchain
class DevchainInterface:
    __dev_chain: DevChainABC
    __port: int
    __w3: Web3
    __accounts: List[Address]

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

    def deploy(
        self, abi, bytecode, arguments: Iterable, params: TxParams
    ) -> web3.contract.Contract:
        arguments = [self._convert_to_web3_type(arg) for arg in arguments]
        factory = self.__w3.eth.contract(abi=abi, bytecode=bytecode)

        if "from" not in params and self.default_account is None:
            raise ValueError("No from_ account specified and no default account set")

        with _signer_account(
            Address(params["from"]) if "from" in params else self.default_account, self
        ):
            tx_hash = factory.constructor(*arguments).transact(params)

        tx_receipt = self.__w3.eth.wait_for_transaction_receipt(tx_hash)
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

    def fallback(
        self,
        contract,
        data: bytes,
        params: TxParams,
        return_tx: bool,
        request_type: RequestType,
    ) -> Any:
        if not params:
            params = {}
        if "from" not in params and self.default_account is None:
            raise ValueError("No from_ account specified and no default account set")

        # set the to address to the value of contract on which the fallback function is called
        params["to"] = contract.address
        if data:
            params[
                "data"
            ] = data  # eth_abi.encode(*arguments, *types) #eth_abi.encode(['uint256', 'address'], [666, contract.address]) #self.__w3.eth.default_account])
        # TODO process the transaction inside the devhcain class and return

        with _signer_account(
            Address(params["from"]) if "from" in params else self.default_account, self
        ):
            tx_hash = self.__w3.eth.send_transaction(params)

        output = self.dev_chain.retrieve_transaction_data([], tx_hash, request_type)
        return bytes.fromhex(output)

    def transact(
        self,
        contract: web3.contract.Contract,
        selector: HexStr,
        arguments: Iterable,
        params: TxParams,
        return_tx,
        request_type,
        return_type: Type,
    ) -> Any:
        arguments = [self._convert_to_web3_type(arg) for arg in arguments]
        func = contract.get_function_by_selector(selector)(*arguments)
        output_abi = get_abi_output_types(func.abi)

        if "from" not in params and self.default_account is None:
            raise ValueError("No from_ account specified and no default account set")

        with _signer_account(
            Address(params["from"]) if "from" in params else self.default_account, self
        ):
            tx_hash = func.transact(params)

        output = self.dev_chain.retrieve_transaction_data([], tx_hash, request_type)
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
    _abi: Any
    _bytecode: HexStr
    _contract: web3.contract.Contract

    def __init__(self, addr: Union[Address, str]):
        self._contract = dev_interface.create_factory(addr, self.__class__._abi)

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
    ) -> "Contract":
        params = {}
        if from_ is not None:
            params["from"] = Address(from_)
        params["value"] = value

        contract = dev_interface.deploy(cls._abi, cls._bytecode, arguments, params)
        return cls(contract.address)

    def transact(
        self,
        selector: HexStr,
        arguments: Iterable,
        return_tx: bool,
        request_type: RequestType,
        return_type: Type,
        from_: Optional[Union[Address, str]],
        to: Optional[Union[Address, str, "Contract"]],
        value: Wei,
    ) -> Any:
        if return_tx:
            raise NotImplementedError("returning a transaction is not implemented")
        params = {}
        if from_ is not None:
            params["from"] = Address(from_)
        params["value"] = value

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
        )

    # TODO handle return data
    def fallback_handler(
        self,
        arguments: Sequence,
        params: TxParams,
        return_tx: bool,
        request_type: RequestType,
    ) -> Any:
        return dev_interface.fallback(
            self._contract,
            arguments[0] if arguments else b"",
            params,
            return_tx,
            request_type,
        )

    def call(
        self,
        selector: HexStr,
        arguments: Iterable,
        return_tx: bool,
        return_type: Type,
        from_: Optional[Union[Address, str]],
        to: Optional[Union[Address, str, "Contract"]],
        value: Wei,
    ) -> Any:
        if return_tx:
            raise ValueError("transaction can't be returned from a call")
        params = {}
        if from_ is not None:
            params["from"] = Address(from_)
        params["value"] = value

        if to is not None:
            if isinstance(to, Contract):
                to = to._contract.address
            params["to"] = to
        return dev_interface.call(
            self._contract, selector, arguments, params, return_type
        )
