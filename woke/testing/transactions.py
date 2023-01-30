from __future__ import annotations

import functools
import time
from abc import ABC, abstractmethod
from enum import IntEnum
from typing import TYPE_CHECKING, Any, Dict, Generic, List, Optional, Type, TypeVar

if TYPE_CHECKING:
    from .blocks import Block

from .call_trace import CallTrace
from .chain_interfaces import (
    AnvilChainInterface,
    GanacheChainInterface,
    HardhatChainInterface,
)
from .core import Account, Chain, default_chain
from .internal import (
    TransactionRevertedError,
    UnknownEvent,
    UnknownTransactionRevertedError,
    read_from_memory,
)
from .json_rpc.communicator import JsonRpcError, TxParams

T = TypeVar("T")


class TransactionStatusEnum(IntEnum):
    PENDING = -1
    SUCCESS = 1
    FAILURE = 0


class TransactionTypeEnum(IntEnum):
    LEGACY = 0
    EIP2930 = 1
    EIP1559 = 2


def _fetch_tx_data(f):
    @functools.wraps(f)
    def wrapper(self: TransactionAbc):
        if self._tx_data is None:
            self._tx_data = self._chain.chain_interface.get_transaction(self.tx_hash)
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
    _tx_params: TxParams
    _chain: Chain
    _abi: Optional[Dict]
    _return_type: Type
    _tx_data: Optional[Dict[str, Any]]
    _tx_receipt: Optional[Dict[str, Any]]
    _trace_transaction: Optional[List[Dict[str, Any]]]
    _debug_trace_transaction = Optional[Dict[str, Any]]
    _error: Optional[TransactionRevertedError]
    _events: Optional[List]

    def __init__(
        self,
        tx_hash: str,
        tx_params: TxParams,
        abi: Optional[Dict],
        return_type: Type,
        chain: Optional[Chain] = None,
    ):
        self._tx_hash = tx_hash
        self._tx_params = tx_params
        self._abi = abi
        self._return_type = return_type
        if chain is None:
            chain = default_chain
        self._chain = chain

        self._tx_data = None
        self._tx_receipt = None
        self._trace_transaction = None
        self._debug_trace_transaction = None
        self._error = None
        self._events = None

    @property
    def tx_hash(self) -> str:
        return self._tx_hash

    @property
    def chain(self) -> Chain:
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
    def block(self) -> Block:
        return self._chain.blocks[self.block_number]

    @property
    def data(self) -> bytes:
        return self._tx_params["data"] if "data" in self._tx_params else b""

    @property
    def from_(self) -> Account:
        return Account(
            self._tx_params["from"], self._chain
        )  # pyright: reportTypedDictNotRequiredAccess=false

    @property
    def to(self) -> Optional[Account]:
        if "to" in self._tx_params:
            return Account(self._tx_params["to"], self._chain)
        return None

    @property
    def gas(self) -> int:
        return self._tx_params["gas"]  # pyright: reportTypedDictNotRequiredAccess=false

    @property
    def nonce(self) -> int:
        return self._tx_params[
            "nonce"
        ]  # pyright: reportTypedDictNotRequiredAccess=false

    @property
    @_fetch_tx_data
    def tx_index(self) -> int:
        return int(
            self._tx_data["transactionIndex"], 16
        )  # pyright: reportOptionalSubscript=false

    @property
    def value(self) -> int:
        return self._tx_params[
            "value"
        ]  # pyright: reportTypedDictNotRequiredAccess=false

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
            receipt = self._chain.chain_interface.get_transaction_receipt(self._tx_hash)
            if receipt is None:
                return TransactionStatusEnum.PENDING
            else:
                self._tx_receipt = receipt

        if int(self._tx_receipt["status"], 16) == 0:
            return TransactionStatusEnum.FAILURE
        else:
            return TransactionStatusEnum.SUCCESS

    def wait(self) -> None:
        while self.status == TransactionStatusEnum.PENDING:
            pass

    def _fetch_trace_transaction(self) -> None:
        if self._trace_transaction is None:
            chain_interface = self._chain.chain_interface
            assert isinstance(chain_interface, AnvilChainInterface)
            self._trace_transaction = chain_interface.trace_transaction(self._tx_hash)

    def _fetch_debug_trace_transaction(self) -> None:
        if self._debug_trace_transaction is None:
            self._debug_trace_transaction = (
                self._chain.chain_interface.debug_trace_transaction(
                    self._tx_hash,
                    {"enableMemory": True},
                )
            )

    @property
    @_fetch_tx_receipt
    def console_logs(self) -> list:
        chain_interface = self._chain.chain_interface

        if isinstance(chain_interface, AnvilChainInterface):
            self._fetch_trace_transaction()
            assert self._trace_transaction is not None
            return self._chain._process_console_logs(self._trace_transaction)
        else:
            raise NotImplementedError

    @property
    @_fetch_tx_receipt
    def events(self) -> list:
        if self._events is not None:
            return self._events

        assert self._tx_receipt is not None

        if len(self._tx_receipt["logs"]) == 0:
            self._events = []
            return self._events

        self._events = self._chain._process_events(self, self._tx_receipt["logs"])
        return self._events

    @property
    @_fetch_tx_receipt
    def raw_events(self) -> List[UnknownEvent]:
        assert self._tx_receipt is not None

        ret = []
        for log in self._tx_receipt["logs"]:
            topics = [
                bytes.fromhex(t[2:]) if t.startswith("0x") else bytes.fromhex(t)
                for t in log["topics"]
            ]
            data = (
                bytes.fromhex(log["data"][2:])
                if log["data"].startswith("0x")
                else bytes.fromhex(log["data"])
            )
            ret.append(UnknownEvent(topics, data))
        return ret

    @property
    @_fetch_tx_receipt
    def error(self) -> Optional[TransactionRevertedError]:
        if self.status == TransactionStatusEnum.SUCCESS:
            return None

        if self._error is not None:
            return self._error

        chain_interface = self._chain.chain_interface

        # call with the same parameters should also revert
        try:
            chain_interface.call(self._tx_params)
            assert False, "Call should have reverted"
        except JsonRpcError as e:
            try:
                if isinstance(
                    chain_interface, (AnvilChainInterface, GanacheChainInterface)
                ):
                    revert_data = e.data["data"]
                elif isinstance(chain_interface, HardhatChainInterface):
                    revert_data = e.data["data"]["data"]
                else:
                    raise NotImplementedError

                if revert_data.startswith("0x"):
                    revert_data = revert_data[2:]
            except Exception:
                raise e from None

        try:
            self._chain._process_revert_data(self, bytes.fromhex(revert_data))
        except TransactionRevertedError as e:
            self._error = e
            return e

    @property
    @_fetch_tx_receipt
    def raw_error(self) -> Optional[UnknownTransactionRevertedError]:
        if self.status == TransactionStatusEnum.SUCCESS:
            return None

        chain_interface = self._chain.chain_interface

        # call with the same parameters should also revert
        try:
            chain_interface.call(self._tx_params)
            assert False, "Call should have reverted"
        except JsonRpcError as e:
            try:
                if isinstance(
                    chain_interface, (AnvilChainInterface, GanacheChainInterface)
                ):
                    revert_data = e.data["data"]
                elif isinstance(chain_interface, HardhatChainInterface):
                    revert_data = e.data["data"]["data"]
                else:
                    raise NotImplementedError

                if revert_data.startswith("0x"):
                    revert_data = revert_data[2:]
            except Exception:
                raise e from None

        return UnknownTransactionRevertedError(bytes.fromhex(revert_data))

    @property
    @_fetch_tx_receipt
    def return_value(self) -> T:
        if self.status != TransactionStatusEnum.SUCCESS:
            e = self.error
            assert e is not None
            raise e

        assert self._tx_receipt is not None
        if (
            "contractAddress" in self._tx_receipt
            and self._tx_receipt["contractAddress"] is not None
        ):
            return self._return_type(self._tx_receipt["contractAddress"], self._chain)

        chain_interface = self._chain.chain_interface
        if isinstance(chain_interface, AnvilChainInterface):
            self._fetch_trace_transaction()
            assert self._trace_transaction is not None
            output = bytes.fromhex(self._trace_transaction[0]["result"]["output"][2:])
        elif isinstance(chain_interface, GanacheChainInterface):
            self._fetch_debug_trace_transaction()
            assert self._debug_trace_transaction is not None

            if len(self._debug_trace_transaction["structLogs"]) == 0 or self._debug_trace_transaction["structLogs"][-1]["op"] != "RETURN":  # type: ignore
                output = b""
            else:
                trace: Any = self._debug_trace_transaction["structLogs"][-1]  # type: ignore
                offset = int(trace["stack"][-1], 16)
                length = int(trace["stack"][-2], 16)

                output = read_from_memory(offset, length, trace["memory"])
        else:
            self._fetch_debug_trace_transaction()
            assert self._debug_trace_transaction is not None
            output = bytes.fromhex(self._debug_trace_transaction["returnValue"])  # type: ignore

        if self._abi is None:
            return self._return_type(output)

        if self._return_type == type(None):
            assert len(output) == 0
            return None  # type: ignore
        return self._chain._process_return_data(
            self, output, self._abi, self._return_type
        )

    @property
    @_fetch_tx_receipt
    def call_trace(self) -> CallTrace:
        if self._debug_trace_transaction is None:
            self._fetch_debug_trace_transaction()
        assert self._debug_trace_transaction is not None

        return CallTrace.from_debug_trace(
            self,
            self._debug_trace_transaction,
            self._tx_params,
        )  # pyright: reportGeneralTypeIssues=false

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
    def gas_price(self) -> int:
        assert "gas_price" in self._tx_params
        return self._tx_params["gas_price"]

    @property
    def type(self) -> TransactionTypeEnum:
        assert "type" in self._tx_params and self._tx_params["type"] == 0
        return TransactionTypeEnum.LEGACY
