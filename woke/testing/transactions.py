from __future__ import annotations

import functools
import time
from abc import ABC, abstractmethod
from enum import IntEnum
from typing import Any, Dict, Generic, Optional, TypeVar

from .core import Account, ChainInterface, default_chain

T = TypeVar("T")


class TransactionStatusEnum(IntEnum):
    PENDING = 0
    SUCCESS = 1
    FAILURE = 2


class TransactionTypeEnum(IntEnum):
    LEGACY = 0
    EIP2930 = 1
    EIP1559 = 2


def _fetch_tx_data(f):
    @functools.wraps(f)
    def wrapper(self: TransactionAbc):
        if self._tx_data is None:
            self._tx_data = self._chain.dev_chain.get_transaction(self.tx_hash)
        return f(self)

    return wrapper


def _fetch_tx_receipt(f):
    @functools.wraps(f)
    def wrapper(self: TransactionAbc):
        if self._tx_receipt is None:
            self.wait()
        assert self._tx_receipt is not None
        return f(self)

    return wrapper


class TransactionAbc(ABC, Generic[T]):
    _tx_hash: str
    _chain: ChainInterface
    _tx_data: Optional[Dict[str, Any]]
    _tx_receipt: Optional[Dict[str, Any]]

    def __init__(self, tx_hash: str, chain: Optional[ChainInterface] = None):
        self._tx_hash = tx_hash
        if chain is None:
            chain = default_chain
        self._chain = chain

        self._tx_data = None
        self._tx_receipt = None

    @property
    def tx_hash(self) -> str:
        return self._tx_hash

    @property
    def chain(self) -> ChainInterface:
        return self._chain

    @property
    @_fetch_tx_data
    def block_hash(self) -> str:
        return self._tx_data["blockHash"]  # pyright: reportOptionalSubscript=false

    @property
    @_fetch_tx_data
    def block_number(self) -> int:
        return int(
            self._tx_data["blockNumber"], 16
        )  # pyright: reportOptionalSubscript=false

    @property
    @_fetch_tx_data
    def from_(self) -> Account:
        return Account(
            self._tx_data["from"], self._chain
        )  # pyright: reportOptionalSubscript=false

    @property
    @_fetch_tx_data
    def to(self) -> Account:
        return Account(
            self._tx_data["to"], self._chain
        )  # pyright: reportOptionalSubscript=false

    @property
    @_fetch_tx_data
    def gas(self) -> int:
        return int(self._tx_data["gas"], 16)  # pyright: reportOptionalSubscript=false

    @property
    @_fetch_tx_data
    def nonce(self) -> int:
        return int(self._tx_data["nonce"], 16)  # pyright: reportOptionalSubscript=false

    @property
    @_fetch_tx_data
    def tx_index(self) -> int:
        return int(
            self._tx_data["transactionIndex"], 16
        )  # pyright: reportOptionalSubscript=false

    @property
    @_fetch_tx_data
    def value(self) -> int:
        return int(self._tx_data["value"], 16)  # pyright: reportOptionalSubscript=false

    @property
    @_fetch_tx_data
    def r(self) -> int:
        return int(self._tx_data["r"], 16)  # pyright: reportOptionalSubscript=false

    @property
    @_fetch_tx_data
    def s(self) -> int:
        return int(self._tx_data["s"], 16)  # pyright: reportOptionalSubscript=false

    @property
    @_fetch_tx_receipt
    def gas_used(self) -> int:
        return int(
            self._tx_receipt["gasUsed"], 16
        )  # pyright: reportOptionalSubscript=false

    @property
    @_fetch_tx_receipt
    def cumulative_gas_used(self) -> int:
        return int(
            self._tx_receipt["cumulativeGasUsed"], 16
        )  # pyright: reportOptionalSubscript=false

    @property
    def status(self) -> TransactionStatusEnum:
        if self._tx_receipt is None:
            receipt = self._chain.dev_chain.get_transaction_receipt(self._tx_hash)
            if receipt is None:
                return TransactionStatusEnum.PENDING
            else:
                self._tx_receipt = receipt

        if int(self._tx_receipt["status"], 16) == 0:
            return TransactionStatusEnum.FAILURE
        else:
            return TransactionStatusEnum.SUCCESS

    def wait(self) -> None:
        for _ in range(40):
            if self.status == TransactionStatusEnum.PENDING:
                return

        while self.status == TransactionStatusEnum.PENDING:
            time.sleep(0.25)

    @property
    def console_logs(self) -> list:
        raise NotImplementedError

    @property
    def events(self) -> list:
        raise NotImplementedError

    @property
    def return_value(self) -> T:
        raise NotImplementedError

    @property
    @abstractmethod
    def type(self) -> TransactionTypeEnum:
        ...


class LegacyTransaction(TransactionAbc[T]):
    @property
    @_fetch_tx_data
    def v(self) -> int:
        return int(self._tx_data["v"], 16)  # pyright: reportOptionalSubscript=false

    @property
    @_fetch_tx_data
    def gas_price(self) -> int:
        return int(
            self._tx_data["gasPrice"], 16
        )  # pyright: reportOptionalSubscript=false

    @property
    @_fetch_tx_data
    def type(self) -> TransactionTypeEnum:
        assert (
            int(self._tx_data["type"], 16) == 0
        )  # pyright: reportOptionalSubscript=false
        return TransactionTypeEnum.LEGACY
