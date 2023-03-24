from __future__ import annotations

import collections
import dataclasses
import functools
import importlib
import inspect
import json
import math
import re
from abc import ABC, abstractmethod
from bdb import BdbQuit
from collections import ChainMap, defaultdict
from contextlib import contextmanager
from copy import deepcopy
from enum import Enum, IntEnum
from os import PathLike
from pathlib import Path
from types import MappingProxyType
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
    overload,
)

import eth_abi
import eth_abi.packed
import eth_account
import eth_account.messages
import eth_utils
from Crypto.Hash import BLAKE2b, keccak
from typing_extensions import (
    Annotated,
    Literal,
    TypedDict,
    get_args,
    get_origin,
    get_type_hints,
)

from woke.utils import StrEnum

from . import hardhat_console
from .blocks import ChainBlocks
from .chain_interfaces import (
    AnvilChainInterface,
    ChainInterfaceAbc,
    GanacheChainInterface,
    GethChainInterface,
    HardhatChainInterface,
    TxParams,
)
from .globals import get_config, get_coverage_handler, get_exception_handler
from .internal import UnknownEvent, read_from_memory
from .json_rpc.communicator import JsonRpcError
from .primitive_types import Length, ValueRange

if TYPE_CHECKING:
    from .transactions import TransactionAbc


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
# list of pairs of (creation code segments, contract_fqn)
# where creation code segments is a tuple of (length, BLAKE2b hash)
creation_code_index: List[Tuple[Tuple[Tuple[int, bytes], ...], str]] = []


eth_account.Account.enable_unaudited_hdwallet_features()


def get_contracts_by_fqn() -> Dict[str, Any]:
    return contracts_by_fqn


class RevertToSnapshotFailedError(Exception):
    pass


class NotConnectedError(Exception):
    pass


class AlreadyConnectedError(Exception):
    pass


class TransactionConfirmationFailedError(Exception):
    pass


class RequestType(StrEnum):
    ACCESS_LIST = "access_list"
    CALL = "call"
    ESTIMATE = "estimate"
    TX = "tx"


def fix_library_abi(args: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ret = []
    for arg in args:
        arg = deepcopy(arg)
        if arg["type"] == "tuple":
            fix_library_abi(arg["components"])
        elif arg["internalType"].startswith("contract "):
            arg["type"] = "address"
        elif arg["internalType"].startswith("enum "):
            arg["type"] = "uint8"
        ret.append(arg)
    return ret


class Abi:
    @staticmethod
    def _normalize_arguments(arguments: Iterable) -> List:
        ret = []
        for arg in arguments:
            if isinstance(arg, Address):
                ret.append(str(arg))
            elif isinstance(arg, Account):
                ret.append(str(arg.address))
            else:
                ret.append(arg)
        return ret

    @classmethod
    def encode(cls, types: Iterable, arguments: Iterable) -> bytes:
        return eth_abi.encode(  # pyright: ignore[reportPrivateImportUsage]
            types, cls._normalize_arguments(arguments)
        )

    @classmethod
    def encode_packed(cls, types: Iterable, arguments: Iterable) -> bytes:
        return (
            eth_abi.packed.encode_packed(  # pyright: ignore[reportPrivateImportUsage]
                types, cls._normalize_arguments(arguments)
            )
        )

    @classmethod
    def encode_with_selector(
        cls, selector: bytes, types: Iterable, arguments: Iterable
    ) -> bytes:
        return selector + cls.encode(types, arguments)

    @classmethod
    def encode_with_signature(
        cls, signature: str, types: Iterable, arguments: Iterable
    ) -> bytes:
        selector = keccak.new(data=signature.encode("utf-8"), digest_bits=256).digest()[
            :4
        ]
        return cls.encode_with_selector(selector, types, arguments)

    @classmethod
    def encode_call(cls, func: Callable, arguments: Iterable) -> bytes:
        def get_class_that_defined_method(meth):
            if isinstance(meth, functools.partial):
                return get_class_that_defined_method(meth.func)
            if inspect.ismethod(meth):
                for c in inspect.getmro(meth.__self__.__class__):
                    if meth.__name__ in c.__dict__:
                        return c
                meth = getattr(
                    meth, "__func__", meth
                )  # fallback to __qualname__ parsing
            if inspect.isfunction(meth):
                c = getattr(
                    inspect.getmodule(meth),
                    meth.__qualname__.split(".<locals>", 1)[0].rsplit(".", 1)[0],
                    None,
                )
                if isinstance(c, type):
                    return c
            return getattr(
                meth, "__objclass__", None
            )  # handle special descriptor objects

        selector = func.selector
        contract = get_class_that_defined_method(func)
        assert selector in contract._abi  # pyright: reportOptionalMemberAccess=false
        types = [
            eth_utils.abi.collapse_if_tuple(cast(Dict[str, Any], arg))
            for arg in fix_library_abi(
                contract._abi[selector]["inputs"]
            )  # pyright: reportOptionalMemberAccess=false
        ]
        return cls.encode_with_selector(selector, types, arguments)

    @classmethod
    def decode(cls, types: Iterable, data: bytes) -> Any:
        return eth_abi.decode(types, data)  # pyright: ignore[reportPrivateImportUsage]


class Wei(int):
    def to_ether(self) -> float:
        return self / 10**18

    def to_gwei(self) -> float:
        return self / 10**9

    @classmethod
    def from_ether(cls, value: Union[int, float]) -> Wei:
        return cls(int(value * 10**18))

    @classmethod
    def from_gwei(cls, value: Union[int, float]) -> Wei:
        return cls(int(value * 10**9))

    @classmethod
    def from_str(cls, value: str) -> Wei:
        count, unit = value.split()
        return cls(eth_utils.to_wei(float(count), unit))


@functools.total_ordering
class Address:
    ZERO: Address

    def __init__(self, address: Union[str, int]) -> None:
        if isinstance(address, int):
            self._address = format(address, "#042x")
        elif isinstance(address, str):
            if not address.startswith(("0x", "0X")):
                address = "0x" + address
            if not eth_utils.is_address(
                address
            ):  # pyright: reportPrivateImportUsage=false
                raise ValueError(f"{address} is not a valid address")
            self._address = address
        else:
            raise TypeError("Expected a string or int")

    def __str__(self) -> str:
        return self._address

    def __repr__(self) -> str:
        return self._address

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, Address):
            return self._address.lower() == other._address.lower()
        elif isinstance(other, str):
            return self._address.lower() == other.lower()
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
            return int(self._address, 16) < int(other, 16)
        elif isinstance(other, Account):
            raise TypeError(
                "Cannot compare Address and Account. Use Account.address instead"
            )
        else:
            return NotImplemented

    def __hash__(self) -> int:
        return hash(self._address.lower())

    def __bytes__(self) -> bytes:
        return bytes.fromhex(self._address[2:])


Address.ZERO = Address(0)


@functools.total_ordering
class Account:
    _address: Address
    _chain: Chain

    def __init__(
        self, address: Union[Address, str, int], chain: Optional[Chain] = None
    ) -> None:
        if chain is None:
            import woke.deployment
            import woke.testing

            if (
                woke.deployment.default_chain.connected
                and woke.testing.default_chain.connected
            ):
                raise ValueError(
                    "Both default_chain and woke.deployment.default_chain are connected. Please specify which chain to use."
                )
            if woke.deployment.default_chain.connected:
                chain = woke.deployment.default_chain
            elif woke.testing.default_chain.connected:
                chain = woke.testing.default_chain
            else:
                raise NotConnectedError("default_chain not connected")

        if isinstance(address, Address):
            self._address = address
        else:
            self._address = Address(address)
        self._chain = chain

    def __str__(self) -> str:
        return self._chain._labels.get(self._address, str(self._address))

    __repr__ = __str__

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, Account):
            return self._address == other._address and self._chain == other._chain
        elif isinstance(other, Address):
            raise TypeError(
                "Cannot compare Account to Address. Use Account.address == Address"
            )
        return NotImplemented

    def __lt__(self, other):
        if isinstance(other, Account):
            if self._chain == other._chain:
                return self._address < other._address
            else:
                raise TypeError(
                    "Cannot compare Accounts from different chains. Compare Account.address instead"
                )
        elif isinstance(other, Address):
            raise TypeError(
                "Cannot compare Account to Address. Use Account.address == Address"
            )
        return NotImplemented

    def __hash__(self) -> int:
        return hash((self._address, self._chain))

    @classmethod
    def new(cls, chain: Optional[Chain] = None) -> Account:
        acc = eth_account.Account.create()
        ret = cls(acc.address, chain)
        ret.chain._private_keys[ret.address] = bytes(acc.key)
        return ret

    @classmethod
    def from_key(
        cls, private_key: Union[str, int, bytes], chain: Optional[Chain] = None
    ) -> Account:
        acc = eth_account.Account.from_key(private_key)
        ret = cls(acc.address, chain)
        ret.chain._private_keys[ret.address] = bytes(acc.key)
        return ret

    @classmethod
    def from_mnemonic(
        cls,
        mnemonic: str,
        passphrase: str = "",
        path: str = "m/44'/60'/0'/0/0",
        chain: Optional[Chain] = None,
    ) -> Account:
        acc = eth_account.Account.from_mnemonic(mnemonic, passphrase, path)
        ret = cls(acc.address, chain)
        ret.chain._private_keys[ret.address] = bytes(acc.key)
        return ret

    @classmethod
    def from_alias(
        cls,
        alias: str,
        password: Optional[str] = None,
        keystore: Optional[PathLike] = None,
        chain: Optional[Chain] = None,
    ) -> Account:
        if keystore is None:
            path = Path(get_config().global_data_path) / "keystore"
        else:
            path = Path(keystore)
        if not path.is_dir():
            raise ValueError(f"Keystore path {path} is not a directory")

        path = path / f"{alias}.json"
        if not path.exists():
            raise ValueError(f"Alias {alias} not found in keystore {path}")

        with path.open() as f:
            data = json.load(f)

        if not data["address"].startswith("0x"):
            data["address"] = "0x" + data["address"]

        if password is None:
            import click

            password = click.prompt(
                f"Password for account {alias}", default="", hide_input=True
            )

        key = eth_account.Account.decrypt(data, password)

        ret = cls(data["address"], chain)
        ret.chain._private_keys[ret.address] = bytes(key)
        return ret

    @property
    def private_key(self) -> Optional[bytes]:
        return self._chain._private_keys.get(self._address, None)

    @property
    def address(self) -> Address:
        return self._address

    @property
    def label(self) -> Optional[str]:
        return self._chain._labels.get(self._address, None)

    @label.setter
    def label(self, value: Optional[str]) -> None:
        if value is not None and not isinstance(value, str):
            raise TypeError("label must be a string or None")
        if value is None:
            del self._chain._labels[self._address]
        else:
            self._chain._labels[self._address] = value

    @property
    def balance(self) -> Wei:
        return Wei(self._chain.chain_interface.get_balance(str(self._address)))

    @balance.setter
    def balance(self, value: int) -> None:
        if not isinstance(value, int):
            raise TypeError("value must be an integer")
        if value < 0:
            raise ValueError("value must be non-negative")
        self._chain.chain_interface.set_balance(str(self.address), value)

    @property
    def code(self) -> bytes:
        return self._chain.chain_interface.get_code(str(self._address))

    @code.setter
    def code(self, value: Union[bytes, bytearray]) -> None:
        if not isinstance(value, (bytes, bytearray)):
            raise TypeError("value must be a bytes object")
        self._chain.chain_interface.set_code(str(self.address), value)

    @property
    def chain(self) -> Chain:
        return self._chain

    @property
    def nonce(self) -> int:
        return self._chain.chain_interface.get_transaction_count(str(self._address))

    @nonce.setter
    def nonce(self, value: int) -> None:
        if not isinstance(value, int):
            raise TypeError("value must be an integer")
        if value < 0:
            raise ValueError("value must be non-negative")
        self._chain.chain_interface.set_nonce(str(self.address), value)
        self._chain._update_nonce(self.address, value)

    def _setup_tx_params(
        self,
        request_type: RequestType,
        data: Union[bytes, bytearray],
        value: Union[int, str],
        from_: Optional[Union[Account, Address, str]],
        gas_limit: Optional[Union[int, Literal["max"], Literal["auto"]]],
        gas_price: Optional[Union[int, str]],
        max_fee_per_gas: Optional[Union[int, str]],
        max_priority_fee_per_gas: Optional[Union[int, str]],
        access_list: Optional[
            Union[Dict[Union[Account, Address, str], List[int]], Literal["auto"]]
        ],
        type: Optional[int],
    ):
        if isinstance(value, str):
            value = Wei.from_str(value)

        params: TxParams = {
            "data": data,
            "value": value,
            "to": str(self._address),
        }
        if from_ is None:
            if request_type == RequestType.CALL:
                from_ = self._chain.default_call_account
            elif request_type == RequestType.TX:
                from_ = self._chain.default_tx_account
            elif request_type == RequestType.ESTIMATE:
                from_ = self._chain.default_estimate_account
            elif request_type == RequestType.ACCESS_LIST:
                from_ = self._chain.default_access_list_account

        if isinstance(from_, Account):
            if from_.chain != self._chain:
                raise ValueError("`from_` account must belong to this chain")
            params["from"] = str(from_.address)
        elif isinstance(from_, (Address, str)):
            params["from"] = str(from_)
        else:
            raise TypeError("`from_` must be an Account, Address, or str")

        if gas_limit == "max":
            params["gas"] = self._chain.block_gas_limit
        elif gas_limit == "auto":
            params["gas"] = "auto"
        elif isinstance(gas_limit, int):
            params["gas"] = gas_limit
        elif gas_limit is None:
            pass
        else:
            raise TypeError("`gas_limit` must be an int, 'max', 'auto', or None")

        if gas_price is not None:
            if isinstance(gas_price, str):
                gas_price = Wei.from_str(gas_price)
            params["gasPrice"] = gas_price

        if max_fee_per_gas is not None:
            if isinstance(max_fee_per_gas, str):
                max_fee_per_gas = Wei.from_str(max_fee_per_gas)
            params["maxFeePerGas"] = max_fee_per_gas

        if max_priority_fee_per_gas is not None:
            if isinstance(max_priority_fee_per_gas, str):
                max_priority_fee_per_gas = Wei.from_str(max_priority_fee_per_gas)
            params["maxPriorityFeePerGas"] = max_priority_fee_per_gas

        if access_list == "auto":
            params["accessList"] = "auto"
        elif access_list is not None:
            # normalize access_list, all keys should be Address
            tmp_access_list = defaultdict(list)
            for k, v in access_list.items():
                if isinstance(k, Account):
                    k = k.address
                elif isinstance(k, str):
                    k = Address(k)
                elif not isinstance(k, Address):
                    raise TypeError("access_list keys must be Account, Address or str")
                tmp_access_list[k].extend(v)
            access_list = tmp_access_list
            params["accessList"] = [
                {"address": str(k), "storageKeys": [hex(i) for i in v]}
                for k, v in access_list.items()
            ]

        if type is not None:
            params["type"] = type

        return params

    def call(
        self,
        data: Union[bytes, bytearray] = b"",
        value: Union[int, str] = 0,
        from_: Optional[Union[Account, Address, str]] = None,
        gas_limit: Optional[Union[int, Literal["max"], Literal["auto"]]] = None,
        gas_price: Optional[Union[int, str]] = None,
        max_fee_per_gas: Optional[Union[int, str]] = None,
        max_priority_fee_per_gas: Optional[Union[int, str]] = None,
        access_list: Optional[
            Union[Dict[Union[Account, Address, str], List[int]], Literal["auto"]]
        ] = None,
        type: Optional[int] = None,
        block: Union[
            int,
            Literal["latest"],
            Literal["pending"],
            Literal["earliest"],
            Literal["safe"],
            Literal["finalized"],
        ] = "latest",
    ) -> bytearray:
        params = self._setup_tx_params(
            RequestType.CALL,
            data,
            value,
            from_,
            gas_limit,
            gas_price,
            max_fee_per_gas,
            max_priority_fee_per_gas,
            access_list,
            type,
        )
        params = self._chain._build_transaction(RequestType.CALL, params, [], None)

        try:
            coverage_handler = get_coverage_handler()
            if coverage_handler is not None and self._chain._debug_trace_call_supported:
                ret = self._chain.chain_interface.debug_trace_call(params, block)
                coverage_handler.add_coverage(params, self._chain, ret)
                output = bytes.fromhex(ret["returnValue"][2:])
                if ret["failed"]:
                    self._chain._process_revert_data(None, output)
                    raise
            else:
                output = self._chain.chain_interface.call(params, block)
        except JsonRpcError as e:
            self._chain._process_call_revert(e)
            raise

        return bytearray(output)

    def estimate(
        self,
        data: Union[bytes, bytearray] = b"",
        value: Union[int, str] = 0,
        from_: Optional[Union[Account, Address, str]] = None,
        gas_limit: Optional[Union[int, Literal["max"], Literal["auto"]]] = None,
        gas_price: Optional[Union[int, str]] = None,
        max_fee_per_gas: Optional[Union[int, str]] = None,
        max_priority_fee_per_gas: Optional[Union[int, str]] = None,
        access_list: Optional[
            Union[Dict[Union[Account, Address, str], List[int]], Literal["auto"]]
        ] = None,
        type: Optional[int] = None,
        block: Union[
            int,
            Literal["latest"],
            Literal["pending"],
            Literal["earliest"],
            Literal["safe"],
            Literal["finalized"],
        ] = "pending",
    ) -> int:
        params = self._setup_tx_params(
            RequestType.ESTIMATE,
            data,
            value,
            from_,
            gas_limit,
            gas_price,
            max_fee_per_gas,
            max_priority_fee_per_gas,
            access_list,
            type,
        )
        params = self._chain._build_transaction(RequestType.CALL, params, [], None)

        try:
            return self._chain.chain_interface.estimate_gas(params, block)
        except JsonRpcError as e:
            self._chain._process_call_revert(e)
            raise

    def access_list(
        self,
        data: Union[bytes, bytearray] = b"",
        value: Union[int, str] = 0,
        from_: Optional[Union[Account, Address, str]] = None,
        gas_limit: Optional[Union[int, Literal["max"], Literal["auto"]]] = None,
        gas_price: Optional[Union[int, str]] = None,
        max_fee_per_gas: Optional[Union[int, str]] = None,
        max_priority_fee_per_gas: Optional[Union[int, str]] = None,
        type: Optional[int] = None,
        block: Union[
            int,
            Literal["latest"],
            Literal["pending"],
            Literal["earliest"],
            Literal["safe"],
            Literal["finalized"],
        ] = "pending",
    ):
        params = self._setup_tx_params(
            RequestType.ACCESS_LIST,
            data,
            value,
            from_,
            gas_limit,
            gas_price,
            max_fee_per_gas,
            max_priority_fee_per_gas,
            {},
            type,
        )
        params = self._chain._build_transaction(
            RequestType.ACCESS_LIST, params, [], None
        )

        try:
            response = self._chain.chain_interface.create_access_list(params, block)
            return {
                Address(e["address"]): [int(s, 16) for s in e["storageKeys"]]
                for e in response["accessList"]
            }, int(response["gasUsed"], 16)
        except JsonRpcError as e:
            self._chain._process_call_revert(e)
            raise

    def transact(
        self,
        data: Union[bytes, bytearray] = b"",
        value: Union[int, str] = 0,
        from_: Optional[Union[Account, Address, str]] = None,
        gas_limit: Optional[Union[int, Literal["max"], Literal["auto"]]] = None,
        gas_price: Optional[Union[int, str]] = None,
        max_fee_per_gas: Optional[Union[int, str]] = None,
        max_priority_fee_per_gas: Optional[Union[int, str]] = None,
        access_list: Optional[
            Union[Dict[Union[Account, Address, str], List[int]], Literal["auto"]]
        ] = None,
        type: Optional[int] = None,
        confirmations: Optional[int] = None,
    ) -> TransactionAbc[bytearray]:
        tx_params = self._setup_tx_params(
            RequestType.TX,
            data,
            value,
            from_,
            gas_limit,
            gas_price,
            max_fee_per_gas,
            max_priority_fee_per_gas,
            access_list,
            type,
        )
        tx_params = self._chain._build_transaction(
            RequestType.CALL, tx_params, [], None
        )

        tx_hash = self._chain._send_transaction(tx_params)

        if "type" not in tx_params:
            from .transactions import LegacyTransaction

            tx_type = LegacyTransaction[bytearray]
        elif tx_params["type"] == 1:
            from .transactions import Eip2930Transaction

            tx_type = Eip2930Transaction[bytearray]
        elif tx_params["type"] == 2:
            from .transactions import Eip1559Transaction

            tx_type = Eip1559Transaction[bytearray]
        else:
            raise ValueError(f"Unknown transaction type {tx_params['type']}")

        tx = tx_type(
            tx_hash,
            tx_params,
            None,
            bytearray,
            self.chain,
        )

        coverage_handler = get_coverage_handler()
        if coverage_handler is not None:
            tx._fetch_debug_trace_transaction()
            coverage_handler.add_coverage(
                tx_params, self._chain, tx._debug_trace_transaction
            )

        if confirmations != 0:
            tx.wait(confirmations)

            if self._chain.tx_callback is not None:
                self._chain.tx_callback(tx)

            if tx.error is not None:
                raise tx.error

        return tx

    def sign(self, data: bytes) -> bytes:
        """
        Sign raw data according to EIP-191 type 0x45.
        Specifically, sign(keccak256(b"\x19Ethereum Signed Message:\n" + len(data) + data)) is returned.
        """
        if self._address not in self._chain._private_keys:
            return self._chain.chain_interface.sign(str(self._address), data)
        else:
            return bytes(
                eth_account.Account.sign_message(
                    eth_account.messages.encode_defunct(data),
                    self._chain._private_keys[self._address],
                ).signature
            )

    def sign_hash(self, data_hash: bytes) -> bytes:
        """
        Sign any 32B data (typically keccak256 hash) without prepending any prefix (non EIP-191 compliant).
        This is not recommended for most use cases.
        Specifically, sign(data_hash) is returned.
        """
        if self._address not in self._chain._private_keys:
            raise NotImplementedError(
                "Signing data hash without prefix (non EIP-191 compliant) is not supported for accounts without supplied private key"
            )
        else:
            return bytes(
                eth_account.Account.signHash(
                    data_hash,
                    self._chain._private_keys[self._address],
                ).signature
            )

    def _prepare_eip712_dict(
        self, message: Any, domain: Eip712Domain, client_signing: bool
    ) -> Dict[str, Any]:
        def _get_type(t: Type, options: Optional[Dict[str, Any]] = None) -> str:
            if options is None:
                options = {}

            if get_origin(t) is Annotated:
                args = get_args(t)
                opt = {}

                for arg in args[1:]:
                    if isinstance(arg, Length):
                        opt["length"] = arg.length
                    elif isinstance(arg, ValueRange):
                        opt["min"] = arg.min
                        opt["max"] = arg.max

                return _get_type(args[0], opt)
            elif get_origin(t) is list:
                if "length" in options:
                    return f"{_get_type(get_args(t)[0])}[{options['length']}]"
                else:
                    return f"{_get_type(get_args(t)[0])}[]"
            elif t is int:
                if "min" in options and "max" in options:
                    if options["min"] == 0:
                        bits = math.ceil(math.log2(options["max"] + 1))
                        return f"uint{bits}"
                    else:
                        bits = math.ceil(math.log2(options["max"] - options["min"] + 1))
                        return f"int{bits}"
                else:
                    # kind of fallback, but it's better than nothing
                    return "int256"
            elif t is bytes or t is bytearray:
                if "length" in options:
                    return f"bytes{options['length']}"
                else:
                    return "bytes"
            elif t is str:
                return "string"
            elif issubclass(t, Enum):
                return "uint8"
            elif t is bool:
                return "bool"
            elif issubclass(t, (Account, Address)):
                return "address"
            elif dataclasses.is_dataclass(t):
                return getattr(t, "original_name", t.__name__)
            else:
                raise ValueError(f"Unsupported type {t}")

        def _get_types(t: Type, types: Dict[str, List[Dict[str, str]]]) -> None:
            if not dataclasses.is_dataclass(t):
                return

            name = getattr(t, "original_name", t.__name__)
            if name in types:
                return

            fields = []
            hints = get_type_hints(t, include_extras=True)
            for f in dataclasses.fields(t):
                assert f.name in hints
                fields.append(
                    {
                        "name": f.metadata.get("original_name", f.name),
                        "type": _get_type(hints[f.name]),
                    }
                )

            types[name] = fields

            for f in dataclasses.fields(t):
                assert f.name in hints
                field_type = hints[f.name]
                while (
                    get_origin(field_type) is Annotated
                    or get_origin(field_type) is list
                ):
                    field_type = get_args(field_type)[0]
                if dataclasses.is_dataclass(field_type):
                    _get_types(field_type, types)

        def _get_value(value: Any) -> Any:
            if dataclasses.is_dataclass(value):
                ret = {}
                for f in dataclasses.fields(value):
                    name = f.metadata.get("original_name", f.name)
                    ret[name] = _get_value(getattr(value, f.name))
                return ret
            elif isinstance(value, (list, tuple)):
                return [_get_value(v) for v in value]
            elif isinstance(value, Account):
                return str(value.address)
            elif isinstance(value, Address):
                return str(value)
            elif isinstance(value, IntEnum):
                return int(value)
            elif isinstance(value, (bytes, bytearray)):
                if client_signing:
                    return "0x" + value.hex()
                else:
                    return value
            else:
                return value

        types = {}
        _get_types(type(message), types)

        ret = {
            "types": types,
            "domain": {},
            "primaryType": _get_type(type(message)),
            "message": _get_value(message),
        }

        domain_type = []
        if "name" in domain:
            ret["domain"]["name"] = domain["name"]
            domain_type.append({"name": "name", "type": "string"})
        if "version" in domain:
            ret["domain"]["version"] = domain["version"]
            domain_type.append({"name": "version", "type": "string"})
        if "chainId" in domain:
            ret["domain"]["chainId"] = domain["chainId"]
            domain_type.append({"name": "chainId", "type": "uint256"})
        if "verifyingContract" in domain:
            if isinstance(domain["verifyingContract"], Account):
                ret["domain"]["verifyingContract"] = str(
                    domain["verifyingContract"].address
                )
            else:
                ret["domain"]["verifyingContract"] = str(domain["verifyingContract"])
            domain_type.append({"name": "verifyingContract", "type": "address"})
        if "salt" in domain:
            ret["domain"]["salt"] = "0x" + domain["salt"].hex()
            domain_type.append({"name": "salt", "type": "bytes32"})

        ret["types"]["EIP712Domain"] = domain_type

        return ret

    def sign_structured(
        self, message: Any, domain: Optional[Eip712Domain] = None
    ) -> bytes:
        """
        Sign structured data according to EIP-712. Message can be either a raw dictionary as described in the EIP
        (https://eips.ethereum.org/EIPS/eip-712), or any ABI-compatible dataclass.
        """

        client_signing = self._address not in self._chain._private_keys

        if isinstance(message, collections.MutableMapping):
            if domain is not None:
                raise ValueError(
                    "Domain cannot be specified when message is a dictionary"
                )
        else:
            if domain is None:
                raise ValueError(
                    "Domain must be specified when message is not a dictionary"
                )
            message = self._prepare_eip712_dict(message, domain, client_signing)

        if client_signing:
            return self._chain.chain_interface.sign_typed(str(self._address), message)
        else:
            return bytes(
                eth_account.Account.sign_message(
                    eth_account.messages.encode_structured_data(message),
                    self._chain._private_keys[self._address],
                ).signature
            )


Eip712Domain = TypedDict(
    "Eip712Domain",
    {
        "name": str,
        "version": str,
        "chainId": int,
        "verifyingContract": Union[Account, Address, str],
        "salt": bytes,
    },
    total=False,
)


def check_connected(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if not args[0].connected:
            raise NotConnectedError("Not connected to a chain")
        return f(*args, **kwargs)

    return wrapper


class Chain(ABC):
    _connected: bool
    _chain_interface: ChainInterfaceAbc
    _accounts: List[Account]
    _accounts_set: Set[Account]  # for faster lookup
    _default_call_account: Optional[Account]
    _default_tx_account: Optional[Account]
    _default_estimate_account: Optional[Account]
    _default_access_list_account: Optional[Account]
    _default_tx_type: int
    _default_tx_confirmations: int
    _deployed_libraries: DefaultDict[bytes, List[Library]]
    _single_source_errors: Set[bytes]
    _snapshots: Dict[str, Dict]
    _blocks: ChainBlocks
    _txs: Dict[str, TransactionAbc]
    _chain_id: int
    _labels: Dict[Address, str]
    _private_keys: Dict[Address, bytes]
    _require_signed_txs: bool
    _fork: Optional[str]
    _debug_trace_call_supported: bool

    tx_callback: Optional[Callable[[TransactionAbc], None]]

    @abstractmethod
    def _connect_setup(
        self, min_gas_price: Optional[int], block_base_fee_per_gas: Optional[int]
    ) -> None:
        ...

    @abstractmethod
    def _connect_finalize(self) -> None:
        ...

    @abstractmethod
    def _update_nonce(self, address: Address, nonce: int) -> None:
        ...

    @abstractmethod
    def snapshot(self) -> str:
        ...

    @abstractmethod
    def revert(self, snapshot_id: str) -> None:
        ...

    @abstractmethod
    def _build_transaction(
        self,
        request_type: RequestType,
        params: TxParams,
        arguments: Iterable,
        abi: Optional[Dict],
    ) -> TxParams:
        ...

    @abstractmethod
    def _wait_for_transaction(
        self, tx: TransactionAbc, confirmations: Optional[int]
    ) -> None:
        ...

    @abstractmethod
    def _confirm_transaction(self, tx: TxParams) -> None:
        ...

    @property
    @abstractmethod
    def block_gas_limit(self) -> int:
        ...

    @block_gas_limit.setter
    @abstractmethod
    def block_gas_limit(self, value: int) -> None:
        ...

    @property
    @abstractmethod
    def gas_price(self) -> Wei:
        ...

    @gas_price.setter
    @abstractmethod
    def gas_price(self, value: int) -> None:
        ...

    @property
    @abstractmethod
    def max_priority_fee_per_gas(self) -> Wei:
        ...

    @max_priority_fee_per_gas.setter
    @abstractmethod
    def max_priority_fee_per_gas(self, value: int) -> None:
        ...

    @contextmanager
    @abstractmethod
    def connect(
        self,
        uri: Optional[str] = None,
        *,
        accounts: Optional[int] = None,
        chain_id: Optional[int] = None,
        fork: Optional[str] = None,
        hardfork: Optional[str] = None,
        min_gas_price: Optional[Union[int, str]],
        block_base_fee_per_gas: Optional[Union[int, str]],
    ):
        ...

    def __init__(self):
        self._connected = False

    def _connect(
        self,
        uri: Optional[str] = None,
        *,
        accounts: Optional[int],
        chain_id: Optional[int],
        fork: Optional[str],
        hardfork: Optional[str],
        min_gas_price: Optional[Union[int, str]],
        block_base_fee_per_gas: Optional[Union[int, str]],
    ):
        if self._connected:
            raise AlreadyConnectedError("Already connected to a chain")

        if isinstance(min_gas_price, str):
            min_gas_price = Wei.from_str(min_gas_price)
        if isinstance(block_base_fee_per_gas, str):
            block_base_fee_per_gas = Wei.from_str(block_base_fee_per_gas)

        if uri is None:
            self._chain_interface = ChainInterfaceAbc.launch(
                accounts=accounts,
                chain_id=chain_id,
                fork=fork,
                hardfork=hardfork,
            )
        else:
            if (
                accounts is not None
                or chain_id is not None
                or fork is not None
                or hardfork is not None
            ):
                raise ValueError(
                    "Cannot specify accounts, chain_id, fork or hardfork when connecting to a running chain"
                )
            self._chain_interface = ChainInterfaceAbc.connect(uri)

        try:
            self._connected = True

            try:
                self._chain_interface.debug_trace_call(
                    {
                        "type": 0,
                    }
                )
                self._debug_trace_call_supported = True
            except JsonRpcError:
                self._debug_trace_call_supported = False

            # determine the chain hardfork to set the default tx type
            if isinstance(self._chain_interface, AnvilChainInterface):
                hardfork = self._chain_interface.node_info()["hardFork"]
                if hardfork in {
                    "FRONTIER",
                    "HOMESTEAD",
                    "TANGERINE",
                    "SPURIOUS_DRAGON",
                    "BYZANTIUM",
                    "CONSTANTINOPLE",
                    "PETERSBURG",
                    "ISTANBUL",
                    "MUIR_GLACIER",
                }:
                    self._default_tx_type = 0
                elif hardfork == "BERLIN":
                    self._default_tx_type = 1
                else:
                    self._default_tx_type = 2
            elif isinstance(
                self._chain_interface, (GethChainInterface, HardhatChainInterface)
            ):
                try:
                    self._chain_interface.call(
                        {
                            "type": 2,
                            "maxPriorityFeePerGas": 0,
                        }
                    )
                    self._default_tx_type = 2
                except JsonRpcError:
                    try:
                        self._chain_interface.call(
                            {
                                "type": 1,
                                "accessList": [],
                            }
                        )
                        self._default_tx_type = 1
                    except JsonRpcError:
                        self._default_tx_type = 0
            elif isinstance(self._chain_interface, GanacheChainInterface):
                self._default_tx_type = 0
            else:
                raise NotImplementedError(
                    f"Unknown chain interface type: {type(self._chain_interface)}"
                )

            if block_base_fee_per_gas is not None and not isinstance(
                self._chain_interface, GanacheChainInterface
            ):
                try:
                    self._chain_interface.set_next_block_base_fee_per_gas(
                        block_base_fee_per_gas
                    )
                except JsonRpcError:
                    pass

            self._accounts = [
                Account(acc, self) for acc in self._chain_interface.get_accounts()
            ]
            self._accounts_set = set(self._accounts)
            self._chain_id = self._chain_interface.get_chain_id()
            self._snapshots = {}
            self._deployed_libraries = defaultdict(list)
            self._default_call_account = (
                self._accounts[0] if len(self._accounts) > 0 else None
            )
            self._default_tx_account = None
            self._default_estimate_account = None
            self._default_access_list_account = None
            self._default_tx_confirmations = 1
            self._txs = {}
            self._blocks = ChainBlocks(self)
            self._labels = {}
            self._private_keys = {}
            self._fork = fork

            self._single_source_errors = {
                selector
                for selector, sources in errors.items()
                if len({source for fqn, source in sources.items()}) == 1
            }

            self.tx_callback = None

            self._connect_setup(min_gas_price, block_base_fee_per_gas)

            yield self
        except Exception as e:
            if not isinstance(e, BdbQuit):
                exception_handler = get_exception_handler()
                if exception_handler is not None:
                    exception_handler(e)
                raise
        finally:
            self._connect_finalize()
            self._chain_interface.close()
            self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    @check_connected
    def chain_interface(self) -> ChainInterfaceAbc:
        return self._chain_interface

    @property
    @check_connected
    def chain_id(self) -> int:
        return self._chain_id

    @property
    @check_connected
    def accounts(self) -> Tuple[Account, ...]:
        return tuple(self._accounts)

    @property
    @check_connected
    def txs(self) -> MappingProxyType[str, TransactionAbc]:
        return MappingProxyType(self._txs)

    @property
    @check_connected
    def default_call_account(self) -> Optional[Account]:
        return self._default_call_account

    @default_call_account.setter
    @check_connected
    def default_call_account(self, account: Union[Account, Address, str]) -> None:
        if isinstance(account, Account):
            if account.chain != self:
                raise ValueError("Account is not from this chain")
            self._default_call_account = account
        else:
            self._default_call_account = Account(account, self)

    @property
    @check_connected
    def default_tx_account(self) -> Optional[Account]:
        return self._default_tx_account

    @default_tx_account.setter
    @check_connected
    def default_tx_account(self, account: Union[Account, Address, str]) -> None:
        if isinstance(account, Account):
            if account.chain != self:
                raise ValueError("Account is not from this chain")
            self._default_tx_account = account
        else:
            self._default_tx_account = Account(account, self)

    @property
    @check_connected
    def default_estimate_account(self) -> Optional[Account]:
        return self._default_estimate_account

    @default_estimate_account.setter
    @check_connected
    def default_estimate_account(self, account: Union[Account, Address, str]) -> None:
        if isinstance(account, Account):
            if account.chain != self:
                raise ValueError("Account is not from this chain")
            self._default_estimate_account = account
        else:
            self._default_estimate_account = Account(account, self)

    @property
    @check_connected
    def default_access_list_account(self) -> Optional[Account]:
        return self._default_access_list_account

    @default_access_list_account.setter
    @check_connected
    def default_access_list_account(
        self, account: Union[Account, Address, str]
    ) -> None:
        if isinstance(account, Account):
            if account.chain != self:
                raise ValueError("Account is not from this chain")
            self._default_access_list_account = account
        else:
            self._default_access_list_account = Account(account, self)

    @property
    @check_connected
    def coinbase(self) -> Account:
        return Account(self._chain_interface.get_coinbase(), self)

    @coinbase.setter
    @check_connected
    def coinbase(self, value: Union[Account, Address, str]) -> None:
        if isinstance(value, Account):
            if value.chain != self:
                raise ValueError("Account is not from this chain")
            self._chain_interface.set_coinbase(str(value.address))
        else:
            self._chain_interface.set_coinbase(str(value))

    @property
    @check_connected
    def blocks(self) -> ChainBlocks:
        return self._blocks

    @property
    @check_connected
    def require_signed_txs(self) -> bool:
        return self._require_signed_txs

    @require_signed_txs.setter
    @check_connected
    def require_signed_txs(self, value: bool) -> None:
        self._require_signed_txs = value

    @property
    @check_connected
    def default_tx_type(self) -> int:
        return self._default_tx_type

    @default_tx_type.setter
    @check_connected
    def default_tx_type(self, value: int) -> None:
        if value not in {0, 1, 2}:
            raise ValueError("Invalid transaction type")
        self._default_tx_type = value

    @property
    @check_connected
    def default_tx_confirmations(self) -> int:
        return self._default_tx_confirmations

    @default_tx_confirmations.setter
    @check_connected
    def default_tx_confirmations(self, value: int) -> None:
        if value < 0:
            raise ValueError("Invalid transaction confirmations value")
        self._default_tx_confirmations = value

    @contextmanager
    def change_automine(self, automine: bool):
        if not self._connected:
            raise NotConnectedError("Not connected to a chain")
        automine_was = self._chain_interface.get_automine()
        self._chain_interface.set_automine(automine)
        try:
            yield
        except Exception as e:
            if not isinstance(e, BdbQuit):
                exception_handler = get_exception_handler()
                if exception_handler is not None:
                    exception_handler(e)
                raise
        finally:
            self._chain_interface.set_automine(automine_was)

    @property
    @check_connected
    def automine(self) -> bool:
        return self._chain_interface.get_automine()

    @automine.setter
    @check_connected
    def automine(self, value: bool) -> None:
        self._chain_interface.set_automine(value)

    @check_connected
    def set_next_block_base_fee_per_gas(self, value: Union[int, str]) -> None:
        if isinstance(value, str):
            value = Wei.from_str(value)
        self._chain_interface.set_next_block_base_fee_per_gas(value)

    @check_connected
    def set_min_gas_price(self, value: Union[int, str]) -> None:
        if isinstance(value, str):
            value = Wei.from_str(value)
        self._chain_interface.set_min_gas_price(value)
        self.gas_price = value

    @check_connected
    def set_default_accounts(self, account: Union[Account, Address, str]) -> None:
        if isinstance(account, Account):
            if account.chain != self:
                raise ValueError("Account is not from this chain")
        else:
            account = Account(account, self)

        self._default_call_account = account
        self._default_tx_account = account
        self._default_estimate_account = account
        self._default_access_list_account = account

    @check_connected
    def reset(self) -> None:
        self._chain_interface.reset()

    @check_connected
    def update_accounts(self):
        self._accounts = [
            Account(acc, self) for acc in self._chain_interface.get_accounts()
        ]
        self._accounts_set = set(self._accounts)

    @check_connected
    def mine(self, timestamp_change: Optional[Callable[[int], int]] = None) -> None:
        if timestamp_change is not None:
            block_info = self._chain_interface.get_block("latest")
            assert "timestamp" in block_info
            last_timestamp = int(block_info["timestamp"], 16)
            timestamp = timestamp_change(last_timestamp)
        else:
            timestamp = None

        self._chain_interface.mine(timestamp)

    @contextmanager
    def snapshot_and_revert(self):
        snapshot_id = self.snapshot()
        try:
            yield
        except Exception as e:
            if not isinstance(e, BdbQuit):
                exception_handler = get_exception_handler()
                if exception_handler is not None:
                    exception_handler(e)
                raise
        finally:
            self.revert(snapshot_id)

    def _convert_to_web3_type(self, value: Any) -> Any:
        if dataclasses.is_dataclass(value):
            return tuple(
                self._convert_to_web3_type(getattr(value, f.name))
                for f in dataclasses.fields(value)
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
        elif hasattr(value, "selector") and isinstance(value.selector, bytes):
            instance = value.__self__
            return bytes.fromhex(str(instance.address)[2:]) + value.selector
        else:
            return value

    def _parse_console_log_data(self, data: bytes):
        selector = data[:4]

        if selector not in hardhat_console.abis:
            raise ValueError(f"Unknown selector: {selector.hex()}")
        abi = hardhat_console.abis[selector]

        output_types = [
            eth_utils.abi.collapse_if_tuple(cast(Dict[str, Any], arg))
            for arg in fix_library_abi(abi)
        ]
        decoded_data = list(Abi.decode(output_types, data[4:]))
        for i in range(len(decoded_data)):
            if abi[i]["type"] == "address":
                decoded_data[i] = Account(decoded_data[i], self)

        if len(decoded_data) == 1:
            decoded_data = decoded_data[0]

        return decoded_data

    def _convert_from_web3_type(
        self, tx: Optional[TransactionAbc], value: Any, expected_type: Type
    ) -> Any:
        if isinstance(expected_type, type(None)):
            return None
        elif expected_type is Callable:
            assert isinstance(value, bytes)
            address = Address("0x" + value[:20].hex())
            fqn = get_fqn_from_address(
                address, tx.block.number - 1 if tx is not None else "latest", self
            )
            if fqn not in contracts_by_fqn:
                raise ValueError(f"Unknown contract: {fqn}")

            module_name, attrs = contracts_by_fqn[fqn]
            obj = getattr(importlib.import_module(module_name), attrs[0])
            for attr in attrs[1:]:
                obj = getattr(obj, attr)

            selector = value[20:24]

            for x in dir(obj):
                m = getattr(obj, x)
                if hasattr(m, "selector") and m.selector == selector:
                    return getattr(obj(address, self), x)

            raise ValueError(
                f"Unable to find function with selector {selector.hex()} in contract {fqn}"
            )
        elif get_origin(expected_type) is list:
            return [
                self._convert_from_web3_type(tx, v, get_args(expected_type)[0])
                for v in value
            ]
        elif dataclasses.is_dataclass(expected_type):
            assert isinstance(value, tuple)
            resolved_types = get_type_hints(expected_type)
            field_types = [
                resolved_types[field.name]
                for field in dataclasses.fields(expected_type)
                if field.init
            ]
            assert len(value) == len(field_types)
            converted_values = [
                self._convert_from_web3_type(tx, v, t)
                for v, t in zip(value, field_types)
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

    def _process_revert_data(
        self,
        tx: Optional[TransactionAbc],
        revert_data: bytes,
    ):
        from .transactions import UnknownTransactionRevertedError

        selector = revert_data[0:4]
        if selector not in errors:
            e = UnknownTransactionRevertedError(revert_data)
            e.tx = tx
            raise e from None

        if selector not in self._single_source_errors:
            if tx is None:
                e = UnknownTransactionRevertedError(revert_data)
                e.tx = tx
                raise e from None

            # ambiguous error, try to find the source contract
            debug_trace = self._chain_interface.debug_trace_transaction(
                tx.tx_hash, {"enableMemory": True}
            )
            try:
                fqn_overrides: ChainMap[Address, Optional[str]] = ChainMap()
                for i in range(tx.tx_index):
                    prev_tx = tx.block.txs[i]
                    prev_tx._fetch_debug_trace_transaction()
                    process_debug_trace_for_fqn_overrides(
                        prev_tx,
                        prev_tx._debug_trace_transaction,
                        fqn_overrides,  # pyright: reportGeneralTypeIssues=false
                    )
                fqn = process_debug_trace_for_revert(tx, debug_trace, fqn_overrides)
            except ValueError:
                raise UnknownTransactionRevertedError(revert_data) from None
        else:
            fqn = list(errors[selector].keys())[0]

        module_name, attrs = errors[selector][fqn]
        obj = getattr(importlib.import_module(module_name), attrs[0])
        for attr in attrs[1:]:
            obj = getattr(obj, attr)
        abi = obj._abi

        types = [
            eth_utils.abi.collapse_if_tuple(cast(Dict[str, Any], arg))
            for arg in fix_library_abi(abi["inputs"])
        ]
        decoded = Abi.decode(types, revert_data[4:])
        generated_error = self._convert_from_web3_type(tx, decoded, obj)
        generated_error.tx = tx
        # raise native pytypes exception on transaction revert
        raise generated_error from None

    def _process_events(self, tx: TransactionAbc, logs: List) -> list:
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
            selector = bytes.fromhex(selector.zfill(64))

            if selector not in events:
                continue

            if len(events[selector]) > 1:
                non_unique = True
                break

        if non_unique:
            debug_trace = self._chain_interface.debug_trace_transaction(
                tx.tx_hash, {"enableMemory": True}
            )
            fqn_overrides: ChainMap[Address, Optional[str]] = ChainMap()
            for i in range(tx.tx_index):
                prev_tx = tx.block.txs[i]
                prev_tx._fetch_debug_trace_transaction()
                process_debug_trace_for_fqn_overrides(
                    prev_tx,
                    prev_tx._debug_trace_transaction,
                    fqn_overrides,  # pyright: reportGeneralTypeIssues=false
                )
            event_traces = process_debug_trace_for_events(
                tx, debug_trace, fqn_overrides
            )
            assert len(event_traces) == len(logs)
        else:
            event_traces = [(None, None)] * len(logs)

        for log, (traced_selector, fqn) in zip(logs, event_traces):
            topics = [
                bytes.fromhex(t[2:].zfill(64))
                if t.startswith("0x")
                else bytes.fromhex(t.zfill(64))
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

            for input in fix_library_abi(abi["inputs"]):
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
                    if topic_data.startswith("0x"):
                        topic_data = topic_data[2:]
                    decoded_indexed.append(
                        Abi.decode([topic_type], bytes.fromhex(topic_data.zfill(64)))[0]
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
            generated_event = self._convert_from_web3_type(tx, merged, obj)
            generated_events.append(generated_event)

        return generated_events

    def _process_return_data(
        self, tx: Optional[TransactionAbc], output: bytes, abi: Dict, return_type: Type
    ):
        output_types = [
            eth_utils.abi.collapse_if_tuple(cast(Dict[str, Any], arg))
            for arg in fix_library_abi(abi["outputs"])
        ]
        decoded_data = Abi.decode(output_types, output)
        if isinstance(decoded_data, (list, tuple)) and len(decoded_data) == 1:
            decoded_data = decoded_data[0]
        return self._convert_from_web3_type(tx, decoded_data, return_type)

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

    def _process_console_logs_from_debug_trace(
        self, debug_trace: Dict[str, Any]
    ) -> List:
        hardhat_console_address = Address("0x000000000000000000636F6e736F6c652e6c6f67")
        console_logs = []
        for trace in debug_trace["structLogs"]:
            if trace["op"] == "STATICCALL":
                addr = Address(int(trace["stack"][-2], 16))
                if addr == hardhat_console_address:
                    args_offset = int(trace["stack"][-3], 16)
                    args_size = int(trace["stack"][-4], 16)
                    data = bytes(
                        read_from_memory(args_offset, args_size, trace["memory"])
                    )
                    console_logs.append(self._parse_console_log_data(data))

        return console_logs

    def _process_call_revert(self, e: JsonRpcError):
        if (
            isinstance(self._chain_interface, (AnvilChainInterface, GethChainInterface))
            and e.data["code"] == 3
        ):
            revert_data = e.data["data"]
        elif (
            isinstance(self._chain_interface, GanacheChainInterface)
            and e.data["code"] == -32000
        ):
            revert_data = e.data["data"]
        elif (
            isinstance(self._chain_interface, HardhatChainInterface)
            and e.data["code"] == -32603
        ):
            revert_data = e.data["data"]["data"]
        else:
            raise e from None

        if revert_data.startswith("0x"):
            revert_data = revert_data[2:]

        self._process_revert_data(None, bytes.fromhex(revert_data))

    def _send_transaction(self, tx_params: TxParams) -> str:
        assert "from" in tx_params
        assert "nonce" in tx_params

        self._confirm_transaction(tx_params)

        if self.require_signed_txs:
            key = self._private_keys.get(Address(tx_params["from"]), None)
            tx_params["from"] = eth_utils.to_checksum_address(tx_params["from"])

            if "to" in tx_params:
                tx_params["to"] = eth_utils.to_checksum_address(tx_params["to"])

            if Account(tx_params["from"], self) in self._accounts_set:
                try:
                    tx_hash = self._chain_interface.send_transaction(tx_params)
                except (ValueError, JsonRpcError) as e:
                    try:
                        tx_hash = e.args[0]["data"]["txHash"]
                    except Exception:
                        raise e
            elif key is not None:
                signed_tx = bytes(
                    eth_account.Account.sign_transaction(tx_params, key).rawTransaction
                )
                try:
                    tx_hash = self._chain_interface.send_raw_transaction(signed_tx)
                except (ValueError, JsonRpcError) as e:
                    try:
                        tx_hash = e.args[0]["data"]["txHash"]
                    except Exception:
                        raise e
            else:
                raise ValueError(
                    f"Private key for account {tx_params['from']} not known and is not owned by the connected client either."
                )
            self._update_nonce(Address(tx_params["from"]), tx_params["nonce"] + 1)
        else:
            if isinstance(self.chain_interface, AnvilChainInterface):
                try:
                    tx_hash = self.chain_interface.send_unsigned_transaction(tx_params)
                except (ValueError, JsonRpcError) as e:
                    try:
                        tx_hash = e.args[0]["data"]["txHash"]
                    except Exception:
                        raise e
                self._update_nonce(Address(tx_params["from"]), tx_params["nonce"] + 1)
            else:
                sender = Account(tx_params["from"], self)

                with _signer_account(sender):
                    try:
                        tx_hash = self._chain_interface.send_transaction(tx_params)
                    except (ValueError, JsonRpcError) as e:
                        try:
                            tx_hash = e.args[0]["data"]["txHash"]
                        except Exception:
                            raise e
                    self._update_nonce(sender.address, tx_params["nonce"] + 1)
        return tx_hash

    @check_connected
    def _call(
        self,
        abi: Optional[Dict],
        arguments: Iterable,
        params: TxParams,
        return_type: Type,
        block: Union[int, str],
    ) -> Any:
        tx_params = self._build_transaction(RequestType.CALL, params, arguments, abi)
        try:
            coverage_handler = get_coverage_handler()
            if coverage_handler is not None and self._debug_trace_call_supported:
                ret = self._chain_interface.debug_trace_call(tx_params, block)
                coverage_handler.add_coverage(tx_params, self, ret)
                output = bytes.fromhex(ret["returnValue"][2:])
                if ret["failed"]:
                    self._process_revert_data(None, output)
                    raise
            else:
                output = self._chain_interface.call(tx_params, block)
        except JsonRpcError as e:
            self._process_call_revert(e)
            raise

        # deploy
        if "to" not in params:
            return bytearray(output)

        assert abi is not None
        return self._process_return_data(None, output, abi, return_type)

    @check_connected
    def _estimate(
        self,
        abi: Optional[Dict],
        arguments: Iterable,
        params: TxParams,
        block: Union[int, str],
    ) -> int:
        tx_params = self._build_transaction(
            RequestType.ESTIMATE, params, arguments, abi
        )
        try:
            return self._chain_interface.estimate_gas(tx_params, block)
        except JsonRpcError as e:
            self._process_call_revert(e)
            raise

    @check_connected
    def _access_list(
        self,
        abi: Optional[Dict],
        arguments: Iterable,
        params: TxParams,
        block: Union[int, str],
    ):
        tx_params = self._build_transaction(
            RequestType.ACCESS_LIST, params, arguments, abi
        )
        try:
            response = self._chain_interface.create_access_list(tx_params, block)
            return {
                Address(e["address"]): [int(s, 16) for s in e["storageKeys"]]
                for e in response["accessList"]
            }, int(response["gasUsed"], 16)
        except JsonRpcError as e:
            self._process_call_revert(e)
            raise

    @check_connected
    def _transact(
        self,
        abi: Optional[Dict],
        arguments: Iterable,
        params: TxParams,
        return_tx: bool,
        return_type: Type,
        confirmations: Optional[int],
    ) -> Any:
        tx_params = self._build_transaction(RequestType.TX, params, arguments, abi)

        tx_hash = self._send_transaction(tx_params)

        if "type" not in tx_params:
            from woke.development.transactions import LegacyTransaction

            tx_type = LegacyTransaction[return_type]
        elif tx_params["type"] == 1:
            from woke.development.transactions import Eip2930Transaction

            tx_type = Eip2930Transaction[return_type]
        elif tx_params["type"] == 2:
            from woke.development.transactions import Eip1559Transaction

            tx_type = Eip1559Transaction[return_type]
        else:
            raise ValueError(f"Unknown transaction type {tx_params['type']}")

        tx = tx_type(
            tx_hash,
            tx_params,
            abi,
            return_type,
            self,
        )
        self._txs[tx_hash] = tx

        coverage_handler = get_coverage_handler()
        if coverage_handler is not None:
            tx._fetch_debug_trace_transaction()
            coverage_handler.add_coverage(tx_params, self, tx._debug_trace_transaction)

        if confirmations != 0:
            tx.wait(confirmations)

            if self.tx_callback is not None:
                self.tx_callback(tx)

            if tx.error is not None:
                raise tx.error

        if return_tx:
            return tx

        return tx.return_value


@contextmanager
def _signer_account(sender: Account):
    chain = sender.chain
    chain_interface = chain.chain_interface
    account_created = True
    if sender not in chain.accounts:
        account_created = False
        if isinstance(chain_interface, (AnvilChainInterface, HardhatChainInterface)):
            chain_interface.impersonate_account(str(sender))
        elif isinstance(chain_interface, GanacheChainInterface):
            chain_interface.add_account(str(sender), "")
            chain.update_accounts()
        else:
            raise NotImplementedError()

    try:
        yield
    finally:
        if not account_created and isinstance(
            chain_interface, (AnvilChainInterface, HardhatChainInterface)
        ):
            chain_interface.stop_impersonating_account(str(sender))


def get_fqn_from_creation_code(creation_code: bytes) -> Tuple[str, int]:
    for creation_code_segments, fqn in creation_code_index:

        length, h = creation_code_segments[0]
        if length > len(creation_code):
            continue
        segment_h = BLAKE2b.new(data=creation_code[:length], digest_bits=256).digest()
        if segment_h != h:
            continue

        creation_code = creation_code[length:]
        found = True
        constructor_offset = length

        for length, h in creation_code_segments[1:]:
            if length + 20 > len(creation_code):
                found = False
                break
            creation_code = creation_code[20:]
            segment_h = BLAKE2b.new(
                data=creation_code[:length], digest_bits=256
            ).digest()
            if segment_h != h:
                found = False
                break
            creation_code = creation_code[length:]
            constructor_offset += length + 20

        if found:
            return fqn, constructor_offset

    raise ValueError("Could not find contract definition from creation code")


def get_fqn_from_address(
    addr: Address, block_number: Union[int, str], chain: Chain
) -> Optional[str]:
    code = chain.chain_interface.get_code(str(addr), block_number)
    metadata = code[-53:]
    if metadata in contracts_by_metadata:
        return contracts_by_metadata[metadata]
    else:
        return None


def process_debug_trace_for_fqn_overrides(
    tx: TransactionAbc,
    debug_trace: Dict[str, Any],
    fqn_overrides: ChainMap[Address, Optional[str]],
) -> None:
    if tx.status == 0:
        return

    trace_is_create = [tx.to is None]
    addresses: List[Optional[Address]] = [tx.to.address if tx.to is not None else None]
    fqns: List[Optional[str]] = []

    fqn_overrides.maps.insert(0, {})

    if tx.to is None:
        fqns.append(None)  # contract is not deployed yet
    else:
        if tx.to.address in fqn_overrides:
            fqns.append(fqn_overrides[tx.to.address])
        else:
            fqns.append(
                get_fqn_from_address(tx.to.address, tx.block.number - 1, tx.chain)
            )

    for i, trace in enumerate(debug_trace["structLogs"]):
        if i > 0:
            prev_trace = debug_trace["structLogs"][i - 1]
            if (
                prev_trace["op"] in {"CALL", "CALLCODE", "DELEGATECALL", "STATICCALL"}
                and prev_trace["depth"] == trace["depth"]
            ):
                # precompiled contract was called in the previous trace
                fqn_overrides.maps[1].update(fqn_overrides.maps[0])
                fqn_overrides.maps.pop(0)
                trace_is_create.pop()
                addresses.pop()
                fqns.pop()

        if trace["op"] in {"CALL", "CALLCODE", "DELEGATECALL", "STATICCALL"}:
            trace_is_create.append(False)
            addr = Address(int(trace["stack"][-2], 16))
            addresses.append(addr)
            if addr in fqn_overrides:
                fqns.append(fqn_overrides[addr])
            else:
                fqns.append(get_fqn_from_address(addr, tx.block.number - 1, tx.chain))

            fqn_overrides.maps.insert(0, {})
        elif trace["op"] in {"CREATE", "CREATE2"}:
            offset = int(trace["stack"][-2], 16)
            length = int(trace["stack"][-3], 16)
            creation_code = read_from_memory(offset, length, trace["memory"])

            trace_is_create.append(True)
            addresses.append(None)
            fqns.append(get_fqn_from_creation_code(creation_code)[0])
            fqn_overrides.maps.insert(0, {})
        elif trace["op"] in {"RETURN", "REVERT", "STOP", "SELFDESTRUCT"}:
            if trace["op"] == "SELFDESTRUCT":
                if addresses[-1] is not None:
                    fqn_overrides.maps[0][addresses[-1]] = None

            if trace["op"] != "REVERT" and len(fqn_overrides.maps) > 1:
                fqn_overrides.maps[1].update(fqn_overrides.maps[0])
            fqn_overrides.maps.pop(0)
            addresses.pop()

            if trace_is_create.pop():
                try:
                    addr = Address(
                        int(debug_trace["structLogs"][i + 1]["stack"][-1], 16)
                    )
                    if addr != Address(0):
                        fqn_overrides.maps[0][addr] = fqns[-1]
                except IndexError:
                    pass
            fqns.pop()


def process_debug_trace_for_revert(
    tx: TransactionAbc,
    debug_trace: Dict,
    fqn_overrides: ChainMap[Address, Optional[str]],
) -> str:
    if tx.to is None:
        origin = get_fqn_from_creation_code(tx.data)[0]
    elif tx.to.address in fqn_overrides:
        origin = fqn_overrides[tx.to.address]
    else:
        origin = get_fqn_from_address(tx.to.address, tx.block.number - 1, tx.chain)

    addresses: List[Optional[Address]] = [tx.to.address if tx.to is not None else None]
    fqns: List[Optional[str]] = [origin]
    trace_is_create: List[bool] = [tx.to is None]
    last_revert_origin = None

    for i, trace in enumerate(debug_trace["structLogs"]):
        if i > 0:
            prev_trace = debug_trace["structLogs"][i - 1]
            if (
                prev_trace["op"] in {"CALL", "CALLCODE", "DELEGATECALL", "STATICCALL"}
                and prev_trace["depth"] == trace["depth"]
            ):
                # precompiled contract was called in the previous trace
                fqn_overrides.maps[1].update(fqn_overrides.maps[0])
                fqn_overrides.maps.pop(0)
                addresses.pop()
                fqns.pop()
                trace_is_create.pop()

        if trace["op"] in {"CALL", "CALLCODE", "DELEGATECALL", "STATICCALL"}:
            trace_is_create.append(False)
            addr = Address(int(trace["stack"][-2], 16))
            addresses.append(addr)
            if addr in fqn_overrides:
                fqns.append(fqn_overrides[addr])
            else:
                fqns.append(get_fqn_from_address(addr, tx.block.number - 1, tx.chain))

            fqn_overrides.maps.insert(0, {})
        elif trace["op"] in {"CREATE", "CREATE2"}:
            offset = int(trace["stack"][-2], 16)
            length = int(trace["stack"][-3], 16)
            creation_code = read_from_memory(offset, length, trace["memory"])

            trace_is_create.append(True)
            addresses.append(None)
            fqns.append(get_fqn_from_creation_code(creation_code)[0])
            fqn_overrides.maps.insert(0, {})
        elif trace["op"] == "REVERT":
            pc = trace["pc"]
            fqn_overrides.maps.pop(0)
            fqn = fqns.pop()
            addresses.pop()
            trace_is_create.pop()

            if fqn in contracts_revert_index and pc in contracts_revert_index[fqn]:
                last_revert_origin = fqn
        elif trace["op"] in {"RETURN", "STOP", "SELFDESTRUCT"}:
            if len(fqn_overrides.maps) > 1:
                fqn_overrides.maps[1].update(fqn_overrides.maps[0])
            fqn_overrides.maps.pop(0)
            addresses.pop()

            if trace_is_create.pop():
                try:
                    addr = Address(
                        int(debug_trace["structLogs"][i + 1]["stack"][-1], 16)
                    )
                    if addr != Address(0):
                        fqn_overrides.maps[0][addr] = fqns[-1]
                except IndexError:
                    pass
            fqns.pop()

    if last_revert_origin is None:
        raise ValueError("Could not find revert origin")
    return last_revert_origin


def process_debug_trace_for_events(
    tx: TransactionAbc,
    debug_trace: Dict,
    fqn_overrides: ChainMap[Address, Optional[str]],
) -> List[Tuple[bytes, Optional[str]]]:
    if tx.to is None:
        origin = get_fqn_from_creation_code(tx.data)[0]
    elif tx.to.address in fqn_overrides:
        origin = fqn_overrides[tx.to.address]
    else:
        origin = get_fqn_from_address(tx.to.address, tx.block.number - 1, tx.chain)

    addresses: List[Optional[Address]] = [tx.to.address if tx.to is not None else None]
    fqns: List[Optional[str]] = [origin]
    trace_is_create: List[bool] = [tx.to is None]
    event_fqns = []

    for i, trace in enumerate(debug_trace["structLogs"]):
        if i > 0:
            prev_trace = debug_trace["structLogs"][i - 1]
            if (
                prev_trace["op"] in {"CALL", "CALLCODE", "DELEGATECALL", "STATICCALL"}
                and prev_trace["depth"] == trace["depth"]
            ):
                # precompiled contract was called in the previous trace
                fqn_overrides.maps[1].update(fqn_overrides.maps[0])
                fqn_overrides.maps.pop(0)
                trace_is_create.pop()
                addresses.pop()
                fqns.pop()

        if trace["op"] in {"CALL", "CALLCODE", "DELEGATECALL", "STATICCALL"}:
            trace_is_create.append(False)
            addr = Address(int(trace["stack"][-2], 16))
            addresses.append(addr)
            if addr in fqn_overrides:
                fqns.append(fqn_overrides[addr])
            else:
                fqns.append(get_fqn_from_address(addr, tx.block.number - 1, tx.chain))

            fqn_overrides.maps.insert(0, {})
        elif trace["op"] in {"CREATE", "CREATE2"}:
            offset = int(trace["stack"][-2], 16)
            length = int(trace["stack"][-3], 16)
            creation_code = read_from_memory(offset, length, trace["memory"])

            trace_is_create.append(True)
            addresses.append(None)
            fqns.append(get_fqn_from_creation_code(creation_code)[0])
            fqn_overrides.maps.insert(0, {})
        elif trace["op"] in {"RETURN", "REVERT", "STOP", "SELFDESTRUCT"}:
            if trace["op"] != "REVERT" and len(fqn_overrides.maps) > 1:
                fqn_overrides.maps[1].update(fqn_overrides.maps[0])
            fqn_overrides.maps.pop(0)
            addresses.pop()

            if trace_is_create.pop():
                try:
                    addr = Address(
                        int(debug_trace["structLogs"][i + 1]["stack"][-1], 16)
                    )
                    if addr != Address(0):
                        fqn_overrides.maps[0][addr] = fqns[-1]
                except IndexError:
                    pass
            fqns.pop()
        elif trace["op"] in {"LOG1", "LOG2", "LOG3", "LOG4"}:
            selector = trace["stack"][-3]
            if selector.startswith("0x"):
                selector = selector[2:]
            selector = bytes.fromhex(selector.zfill(64))
            event_fqns.append((selector, fqns[-1]))

    return event_fqns


LIBRARY_PLACEHOLDER_REGEX = re.compile(r"__\$[0-9a-fA-F]{34}\$__")


class Contract(Account):
    _abi: Dict[
        Union[bytes, Literal["constructor"], Literal["fallback"], Literal["receive"]],
        Any,
    ]
    _creation_code: str

    def __init__(
        self, addr: Union[Account, Address, str], chain: Optional[Chain] = None
    ):
        if isinstance(addr, Account):
            if chain is None:
                chain = addr.chain
            elif addr.chain != chain:
                raise ValueError("Account and chain must be from the same chain")
            addr = addr.address
        super().__init__(addr, chain)

    def __str__(self):
        return self._chain._labels.get(
            self.address, f"{self.__class__.__name__}({self.address})"
        )

    __repr__ = __str__

    @classmethod
    def _get_creation_code(
        cls, libraries: Dict[bytes, Tuple[Union[Account, Address], str]]
    ) -> bytes:
        creation_code = cls._creation_code
        for match in LIBRARY_PLACEHOLDER_REGEX.finditer(creation_code):
            lib_id = bytes.fromhex(match.group(0)[3:-3])
            assert (
                lib_id in libraries
            ), f"Address of library {libraries[lib_id][1]} required to generate creation code"

            lib = libraries[lib_id][0]
            if isinstance(lib, Account):
                lib_addr = str(lib.address)[2:]
            elif isinstance(lib, Address):
                lib_addr = str(lib)[2:]
            else:
                raise TypeError()

            creation_code = (
                creation_code[: match.start()] + lib_addr + creation_code[match.end() :]
            )
        return bytes.fromhex(creation_code)

    @classmethod
    def _deploy(
        cls,
        request_type: RequestType,
        arguments: Iterable,
        return_tx: bool,
        return_type: Type,
        from_: Optional[Union[Account, Address, str]],
        value: Union[int, str],
        gas_limit: Optional[Union[int, Literal["max"], Literal["auto"]]],
        libraries: Dict[bytes, Tuple[Union[Account, Address, None], str]],
        chain: Optional[Chain],
        gas_price: Optional[Union[int, str]],
        max_fee_per_gas: Optional[Union[int, str]],
        max_priority_fee_per_gas: Optional[Union[int, str]],
        access_list: Optional[
            Union[Dict[Union[Account, Address, str], List[int]], Literal["auto"]]
        ],
        type: Optional[int],
        block: Optional[Union[int, str]],
        confirmations: Optional[int],
    ) -> Any:
        if chain is None:
            import woke.deployment
            import woke.testing

            if (
                woke.deployment.default_chain.connected
                and woke.testing.default_chain.connected
            ):
                raise ValueError(
                    "Both default_chain and woke.deployment.default_chain are connected. Please specify which chain to use."
                )
            if woke.deployment.default_chain.connected:
                chain = woke.deployment.default_chain
            elif woke.testing.default_chain.connected:
                chain = woke.testing.default_chain
            else:
                raise NotConnectedError("default_chain not connected")

        creation_code = cls._creation_code
        for match in LIBRARY_PLACEHOLDER_REGEX.finditer(creation_code):
            lib_id = bytes.fromhex(match.group(0)[3:-3])
            assert lib_id in libraries

            lib = libraries[lib_id][0]
            if lib is not None:
                if isinstance(lib, Account):
                    lib_addr = str(lib.address)[2:]
                else:
                    lib_addr = str(lib)[2:]
            elif lib_id in chain._deployed_libraries:
                lib_addr = str(chain._deployed_libraries[lib_id][-1].address)[2:]
            else:
                raise ValueError(f"Library {libraries[lib_id][1]} not deployed")

            creation_code = (
                creation_code[: match.start()] + lib_addr + creation_code[match.end() :]
            )

        return cls._execute(
            chain,
            request_type,
            creation_code,
            arguments,
            return_tx,
            return_type,
            from_,
            None,
            value,
            gas_limit,
            gas_price,
            max_fee_per_gas,
            max_priority_fee_per_gas,
            access_list,
            type,
            block,
            confirmations,
        )

    @classmethod
    def _execute(
        cls,
        chain: Chain,
        request_type: RequestType,
        data: str,
        arguments: Iterable,
        return_tx: bool,
        return_type: Type,
        from_: Optional[Union[Account, Address, str]],
        to: Optional[Union[Account, Address, str]],
        value: Union[int, str],
        gas_limit: Optional[Union[int, Literal["max"], Literal["auto"]]],
        gas_price: Optional[Union[int, str]],
        max_fee_per_gas: Optional[Union[int, str]],
        max_priority_fee_per_gas: Optional[Union[int, str]],
        access_list: Optional[
            Union[Dict[Union[Account, Address, str], List[int]], Literal["auto"]]
        ],
        type: Optional[int],
        block: Optional[Union[int, str]],
        confirmations: Optional[int],
    ):
        if request_type == RequestType.TX and block is not None:
            raise ValueError("block cannot be specified for contract transactions")
        if request_type != RequestType.TX and return_tx:
            raise ValueError("return_tx cannot be specified for non-tx requests")
        if request_type != RequestType.TX and confirmations is not None:
            raise ValueError("confirmations cannot be specified for non-tx requests")
        if confirmations == 0 and not return_tx:
            raise ValueError("confirmations=0 is only valid when return_tx=True")
        if request_type == RequestType.ACCESS_LIST and access_list is not None:
            raise ValueError("access_list cannot be specified for access list requests")

        params: TxParams = {}
        if from_ is not None:
            if isinstance(from_, Account):
                if from_.chain != chain:
                    raise ValueError("`from_` account must belong to this chain")
                params["from"] = str(from_.address)
            else:
                params["from"] = str(from_)

        if isinstance(value, str):
            value = Wei.from_str(value)
        params["value"] = value

        if gas_limit == "max":
            params["gas"] = chain.block_gas_limit
        elif gas_limit == "auto":
            params["gas"] = "auto"
        elif isinstance(gas_limit, int):
            params["gas"] = gas_limit
        elif gas_limit is None:
            pass
        else:
            raise TypeError("`gas_limit` must be an int, 'max', 'auto', or None")

        if to is not None:
            if isinstance(to, Account):
                if to.chain != chain:
                    raise ValueError("`to` account must belong to this chain")
                params["to"] = str(to.address)
            else:
                params["to"] = str(to)

        if gas_price is not None:
            if isinstance(gas_price, str):
                gas_price = Wei.from_str(gas_price)
            params["gasPrice"] = gas_price

        if max_fee_per_gas is not None:
            if isinstance(max_fee_per_gas, str):
                max_fee_per_gas = Wei.from_str(max_fee_per_gas)
            params["maxFeePerGas"] = max_fee_per_gas

        if max_priority_fee_per_gas is not None:
            if isinstance(max_priority_fee_per_gas, str):
                max_priority_fee_per_gas = Wei.from_str(max_priority_fee_per_gas)
            params["maxPriorityFeePerGas"] = max_priority_fee_per_gas

        if access_list == "auto":
            params["accessList"] = "auto"
        elif access_list is not None:
            # normalize access_list, all keys should be Address
            tmp_access_list = defaultdict(list)
            for k, v in access_list.items():
                if isinstance(k, Account):
                    k = k.address
                elif isinstance(k, str):
                    k = Address(k)
                elif not isinstance(k, Address):
                    raise TypeError("access_list keys must be Account, Address or str")
                tmp_access_list[k].extend(v)
            access_list = tmp_access_list
            params["accessList"] = [
                {"address": str(k), "storageKeys": [hex(i) for i in v]}
                for k, v in access_list.items()
            ]

        if type is not None:
            params["type"] = type

        params["data"] = bytes.fromhex(data)

        if to is None:
            abi = cls._abi["constructor"] if "constructor" in cls._abi else None
        else:
            abi = cls._abi[params["data"]]

        if request_type == RequestType.TX:
            return chain._transact(
                abi,
                arguments,
                params,
                return_tx,
                return_type,
                confirmations,
            )
        elif request_type == RequestType.CALL:
            if block is None:
                block = "latest"
            return chain._call(abi, arguments, params, return_type, block)
        elif request_type == RequestType.ESTIMATE:
            if block is None:
                block = "pending"

            return chain._estimate(abi, arguments, params, block)
        elif request_type == RequestType.ACCESS_LIST:
            if block is None:
                block = "pending"

            return chain._access_list(abi, arguments, params, block)
        else:
            raise ValueError("invalid request type")


class Library(Contract):
    _library_id: bytes

    @classmethod
    def _deploy(
        cls,
        request_type: RequestType,
        arguments: Iterable,
        return_tx: bool,
        return_type: Type,
        from_: Optional[Union[Account, Address, str]],
        value: Union[int, str],
        gas_limit: Optional[Union[int, Literal["max"], Literal["auto"]]],
        libraries: Dict[bytes, Tuple[Union[Account, Address, None], str]],
        chain: Optional[Chain],
        gas_price: Optional[Union[int, str]],
        max_fee_per_gas: Optional[Union[int, str]],
        max_priority_fee_per_gas: Optional[Union[int, str]],
        access_list: Optional[Dict[Union[Account, Address, str], List[int]]],
        type: Optional[int],
        block: Optional[Union[int, str]],
        confirmations: Optional[int],
    ) -> Any:
        if chain is None:
            import woke.deployment
            import woke.testing

            if (
                woke.deployment.default_chain.connected
                and woke.testing.default_chain.connected
            ):
                raise ValueError(
                    "Both default_chain and woke.deployment.default_chain are connected. Please specify which chain to use."
                )
            if woke.deployment.default_chain.connected:
                chain = woke.deployment.default_chain
            elif woke.testing.default_chain.connected:
                chain = woke.testing.default_chain
            else:
                raise NotConnectedError("default_chain not connected")

        lib = super()._deploy(
            request_type,
            arguments,
            return_tx,
            return_type,
            from_,
            value,
            gas_limit,
            libraries,
            chain,
            gas_price,
            max_fee_per_gas,
            max_priority_fee_per_gas,
            access_list,
            type,
            block,
            confirmations,
        )
        if confirmations != 0:
            if return_tx:
                chain._deployed_libraries[cls._library_id].append(lib.return_value)
            else:
                chain._deployed_libraries[cls._library_id].append(lib)
        return lib
