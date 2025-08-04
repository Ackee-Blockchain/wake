from __future__ import annotations

from os import PathLike
from typing import Dict, List, Sequence, Union, Optional, Any, Callable, Type, Tuple
from typing_extensions import Literal

from wake.development.core import Chain, SignedAuthorization, TransactionAbc, TxParams, Eip712Domain
from wake.development.primitive_types import bytes32


class abi:
    @staticmethod
    def encode(*args) -> bytes: ...

    @staticmethod
    def encode_with_selector(selector: bytes, *args) -> bytes: ...

    @staticmethod
    def encode_with_signature(signature: str, *args) -> bytes: ...

    @staticmethod
    def encode_call(func: Callable, args: Sequence) -> bytes: ...

    @staticmethod
    def encode_packed(*args) -> bytes: ...

    @staticmethod
    def decode(data: bytes, types: Sequence[Type], chain: Optional[Chain] = None): ...


class Abi:
    @staticmethod
    def encode(types: Sequence[str], args: Sequence) -> bytes: ...

    @staticmethod
    def encode_with_selector(selector: bytes, types: Sequence[str], args: Sequence) -> bytes: ...

    @staticmethod
    def encode_with_signature(signature: str, types: Sequence[str], args: Sequence) -> bytes: ...

    @staticmethod
    def encode_packed(types: Sequence[str], args: Sequence) -> bytes: ...

    @staticmethod
    def decode(types: Sequence[str], data: bytes) -> tuple: ...


class Address:
    ZERO: Address

    def __init__(self, address: Union[int, str]) -> None: ...

    def __str__(self) -> str: ...

    def __repr__(self) -> str: ...

    def __bytes__(self) -> bytes: ...

    def __int__(self) -> int: ...

    def __eq__(self, other: Address) -> bool: ...

    def __ne__(self, other: Address) -> bool: ...

    def __lt__(self, other: Address) -> bool: ...

    def __le__(self, other: Address) -> bool: ...

    def __gt__(self, other: Address) -> bool: ...

    def __ge__(self, other: Address) -> bool: ...

    def __hash__(self) -> int: ...

    @classmethod
    def from_key(cls, private_key: Union[str, int, bytes]) -> Address: ...

    @classmethod
    def from_mnemonic(
        cls,
        mnemonic: str,
        passphrase: str = "",
        path: str = "m/44'/60'/0'/0/0",
    ) -> Address:
        ...

    @classmethod
    def from_alias(
        cls,
        alias: str,
        password: Optional[str] = None,
        keystore: Optional[PathLike] = None,
    ) -> Address:
        ...

    @classmethod
    def from_trezor(cls, path: str = "m/44'/60'/0'/0/0") -> Address: ...

    @property
    def private_key(self) -> Optional[bytes]: ...

    def export_keystore(self, alias: str, password: str, keystore: Optional[PathLike] = None) -> None: ...


class Account:
    def __init__(self, address: Union[Address, str, int], chain: Optional[Chain] = None) -> None: ...

    def __str__(self) -> str: ...

    def __repr__(self) -> str: ...

    def __eq__(self, other: Account) -> bool: ...

    def __ne__(self, other: Account) -> bool: ...

    def __lt__(self, other: Account) -> bool: ...

    def __le__(self, other: Account) -> bool: ...

    def __gt__(self, other: Account) -> bool: ...

    def __ge__(self, other: Account) -> bool: ...

    def __hash__(self) -> int: ...

    @classmethod
    def new(cls, chain: Optional[Chain] = None, extra_entropy: bytes = b"") -> Account: ...

    @classmethod
    def from_key(cls, private_key: Union[str, int, bytes], chain: Optional[Chain] = None) -> Account: ...

    @classmethod
    def from_mnemonic(
        cls,
        mnemonic: str,
        passphrase: str = "",
        path: str = "m/44'/60'/0'/0/0",
        chain: Optional[Chain] = None,
    ) -> Account: ...

    @classmethod
    def from_alias(
        cls,
        alias: str,
        password: Optional[str] = None,
        keystore: Optional[PathLike] = None,
        chain: Optional[Chain] = None,
    ) -> Account: ...

    @classmethod
    def from_trezor(cls, path: str = "m/44'/60'/0'/0/0", chain: Optional[Chain] = None) -> Account: ...

    @property
    def private_key(self) -> Optional[bytes]: ...

    @property
    def address(self) -> Address: ...

    @property
    def chain(self) -> Chain: ...

    @property
    def label(self) -> Optional[str]: ...

    @label.setter
    def label(self, label: Optional[str]) -> None: ...

    @property
    def balance(self) -> int: ...  # TODO actually returns Wei

    @balance.setter
    def balance(self, value: Union[int, str]) -> None: ...

    @property
    def code(self) -> bytes: ...

    @code.setter
    def code(self, value: bytes) -> None: ...

    @property
    def nonce(self) -> int: ...

    @nonce.setter
    def nonce(self, value: int) -> None: ...

    def call(
        self,
        data: bytes = b"",
        value: Union[int, str] = 0,
        from_: Optional[Union[Account, Address, str]] = None,
        gas_limit: Optional[Union[int, Literal["max"], Literal["auto"]]] = None,
        gas_price: Optional[Union[int, str]] = None,
        max_fee_per_gas: Optional[Union[int, str]] = None,
        max_priority_fee_per_gas: Optional[Union[int, str]] = None,
        access_list: Optional[
            Union[Dict[Union[Account, Address, str], List[int]], Literal["auto"]]
        ] = None,
        authorization_list: Optional[List[SignedAuthorization]] = None,
        block: Union[
            int,
            Literal["latest"],
            Literal["pending"],
            Literal["earliest"],
            Literal["safe"],
            Literal["finalized"],
        ] = "latest",
    ) -> bytes: ...

    def estimate(
        self,
        data: bytes = b"",
        value: Union[int, str] = 0,
        from_: Optional[Union[Account, Address, str]] = None,
        gas_limit: Optional[Union[int, Literal["max"], Literal["auto"]]] = None,
        gas_price: Optional[Union[int, str]] = None,
        max_fee_per_gas: Optional[Union[int, str]] = None,
        max_priority_fee_per_gas: Optional[Union[int, str]] = None,
        access_list: Optional[
            Union[Dict[Union[Account, Address, str], List[int]], Literal["auto"]]
        ] = None,
        authorization_list: Optional[List[SignedAuthorization]] = None,
        block: Union[
            int,
            Literal["latest"],
            Literal["pending"],
            Literal["earliest"],
            Literal["safe"],
            Literal["finalized"],
        ] = "pending",
        revert_on_failure: bool = True,
    ) -> int: ...

    def access_list(
        self,
        data: bytes = b"",
        value: Union[int, str] = 0,
        from_: Optional[Union[Account, Address, str]] = None,
        gas_limit: Optional[Union[int, Literal["max"], Literal["auto"]]] = None,
        gas_price: Optional[Union[int, str]] = None,
        max_fee_per_gas: Optional[Union[int, str]] = None,
        max_priority_fee_per_gas: Optional[Union[int, str]] = None,
        authorization_list: Optional[List[SignedAuthorization]] = None,
        block: Union[
            int,
            Literal["latest"],
            Literal["pending"],
            Literal["earliest"],
            Literal["safe"],
            Literal["finalized"],
        ] = "pending",
        revert_on_failure: bool = True,
    ) -> Tuple[Dict[Address, List[int]], int]: ...

    def transact(
        self,
        data: bytes = b"",
        value: Union[int, str] = 0,
        from_: Optional[Union[Account, Address, str]] = None,
        gas_limit: Optional[Union[int, Literal["max"], Literal["auto"]]] = None,
        gas_price: Optional[Union[int, str]] = None,
        max_fee_per_gas: Optional[Union[int, str]] = None,
        max_priority_fee_per_gas: Optional[Union[int, str]] = None,
        access_list: Optional[
            Union[Dict[Union[Account, Address, str], List[int]], Literal["auto"]]
        ] = None,
        authorization_list: Optional[List[SignedAuthorization]] = None,
        confirmations: Optional[int] = None,
    ) -> TransactionAbc[bytes]: ...

    def sign(self, data: bytes) -> bytes: ...

    def sign_hash(self, data: bytes) -> bytes: ...

    def sign_transaction(self, tx: TxParams) -> bytes: ...

    def sign_structured(
        self, message: Any, domain: Optional[Eip712Domain] = None
    ) -> bytes: ...

    def sign_authorization(self, address: Union[Account, Address, str, int], chain_id: Optional[int] = None, nonce: Optional[int] = None) -> SignedAuthorization: ...


class Contract(Account):
    def __init__(self, address: Union[Account, Address, str, int], chain: Optional[Chain] = None) -> None: ...

    def __str__(self) -> str: ...

    def __repr__(self) -> str: ...


class Library(Contract):
    pass


def encode_eip712_type(obj) -> str: ...

def encode_eip712_data(obj) -> bytes: ...

def default_chain() -> Chain: ...

def new_mnemonic(words: int, language: str) -> str: ...

def keccak256(data: bytes) -> bytes32: ...

def to_checksum_address(address: Union[Address, Account, str, int]) -> str: ...

def sync_coverage() -> None: ...

def set_coverage_callback(callback: Callable[[Dict[str, Dict[Tuple[int, int], int]]], None]) -> None: ...
