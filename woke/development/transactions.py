from __future__ import annotations

import functools
import inspect
from abc import ABC, abstractmethod
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field, fields
from enum import IntEnum
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    Generic,
    List,
    Optional,
    Tuple,
    Type,
    TypeVar,
    Union,
)

if TYPE_CHECKING:
    from .blocks import Block

from .call_trace import CallTrace
from .chain_interfaces import (
    AnvilChainInterface,
    GanacheChainInterface,
    GethChainInterface,
    HardhatChainInterface,
    TxParams,
)
from .core import Account, Chain, Wei
from .internal import UnknownEvent, read_from_memory
from .json_rpc import JsonRpcError

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
    _raw_error: Optional[UnknownTransactionRevertedError]
    _events: Optional[List]

    def __init__(
        self,
        tx_hash: str,
        tx_params: TxParams,
        abi: Optional[Dict],
        return_type: Type,
        chain: Chain,
    ):
        self._tx_hash = tx_hash
        self._tx_params = tx_params
        self._abi = abi
        self._return_type = return_type
        self._chain = chain

        self._tx_data = None
        self._tx_receipt = None
        self._trace_transaction = None
        self._debug_trace_transaction = None
        self._error = None
        self._raw_error = None
        self._events = None

    @property
    def tx_hash(self) -> str:
        return self._tx_hash

    @property
    def chain(self) -> Chain:
        return self._chain

    @property
    @_fetch_tx_receipt
    def block(self) -> Block:
        return self._chain.blocks[int(self._tx_receipt["blockNumber"], 16)]

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
    def gas_limit(self) -> int:
        return self._tx_params["gas"]  # pyright: reportTypedDictNotRequiredAccess=false

    @property
    def nonce(self) -> int:
        return self._tx_params[
            "nonce"
        ]  # pyright: reportTypedDictNotRequiredAccess=false

    @property
    @_fetch_tx_receipt
    def tx_index(self) -> int:
        return int(
            self._tx_receipt["transactionIndex"], 16
        )  # pyright: reportOptionalSubscript=false

    @property
    def value(self) -> Wei:
        return Wei(
            self._tx_params["value"]
        )  # pyright: reportTypedDictNotRequiredAccess=false

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
    @_fetch_tx_receipt
    def effective_gas_price(self) -> Wei:
        return Wei(
            int(self._tx_receipt["effectiveGasPrice"], 16)
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

    def wait(self, confirmations: Optional[int] = None) -> None:
        self._chain._wait_for_transaction(self, confirmations)

    def _fetch_trace_transaction(self) -> None:
        if self._trace_transaction is None:
            chain_interface = self._chain.chain_interface
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
        elif isinstance(
            chain_interface, (GanacheChainInterface, HardhatChainInterface)
        ):
            self._fetch_debug_trace_transaction()
            assert self._debug_trace_transaction is not None
            return self._chain._process_console_logs_from_debug_trace(
                self._debug_trace_transaction
            )
        elif isinstance(chain_interface, GethChainInterface):
            try:
                self._fetch_trace_transaction()
                assert self._trace_transaction is not None
                return self._chain._process_console_logs(self._trace_transaction)
            except JsonRpcError as e:
                # TODO make assertions about error.code?
                try:
                    self._fetch_debug_trace_transaction()
                    assert self._debug_trace_transaction is not None
                    return self._chain._process_console_logs_from_debug_trace(
                        self._debug_trace_transaction
                    )
                except JsonRpcError as e:
                    # TODO make assertions about error.code?
                    raise RuntimeError(
                        f"Could not get console logs for transaction {self.tx_hash} as trace_transaction and debug_trace_transaction are both unavailable"
                    )
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

        raw_error = self.raw_error
        assert raw_error is not None

        try:
            self._chain._process_revert_data(self, raw_error.data)
        except TransactionRevertedError as e:
            self._error = e
            return e

    @property
    @_fetch_tx_receipt
    def raw_error(self) -> Optional[UnknownTransactionRevertedError]:
        if self.status == TransactionStatusEnum.SUCCESS:
            return None

        if self._raw_error is not None:
            return self._raw_error

        chain_interface = self._chain.chain_interface

        if isinstance(chain_interface, AnvilChainInterface):
            self._fetch_trace_transaction()
            revert_data = bytes.fromhex(
                self._trace_transaction[0]["result"]["output"][2:]
            )
        elif isinstance(chain_interface, GanacheChainInterface):
            self._fetch_debug_trace_transaction()
            assert self._debug_trace_transaction is not None

            if len(self._debug_trace_transaction["structLogs"]) == 0 or self._debug_trace_transaction["structLogs"][-1]["op"] != "REVERT":  # type: ignore
                revert_data = b""
            else:
                trace: Any = self._debug_trace_transaction["structLogs"][-1]  # type: ignore
                offset = int(trace["stack"][-1], 16)
                length = int(trace["stack"][-2], 16)

                revert_data = bytes(read_from_memory(offset, length, trace["memory"]))
        elif isinstance(chain_interface, HardhatChainInterface):
            self._fetch_debug_trace_transaction()
            assert self._debug_trace_transaction is not None
            revert_data = bytes.fromhex(self._debug_trace_transaction["returnValue"])  # type: ignore
        elif isinstance(chain_interface, GethChainInterface):
            try:
                self._fetch_trace_transaction()
                assert self._trace_transaction is not None
                revert_data = bytes.fromhex(
                    self._trace_transaction[0]["result"]["output"][2:]
                )
            except JsonRpcError as e:
                # TODO make assertions about error.code?
                try:
                    self._fetch_debug_trace_transaction()
                    assert self._debug_trace_transaction is not None
                    revert_data = bytes.fromhex(self._debug_trace_transaction["returnValue"])  # type: ignore
                except JsonRpcError as e:
                    # TODO make assertions about error.code?
                    raise RuntimeError(
                        f"Could not get revert reason data for transaction {self.tx_hash} as trace_transaction and debug_trace_transaction are both unavailable"
                    )
        else:
            raise NotImplementedError

        self._raw_error = UnknownTransactionRevertedError(revert_data)
        self._raw_error.tx = self
        return self._raw_error

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

        if self._return_type is type(None):
            return None

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
        elif isinstance(chain_interface, HardhatChainInterface):
            self._fetch_debug_trace_transaction()
            assert self._debug_trace_transaction is not None
            output = bytes.fromhex(self._debug_trace_transaction["returnValue"])  # type: ignore
        elif isinstance(chain_interface, GethChainInterface):
            try:
                self._fetch_trace_transaction()
                assert self._trace_transaction is not None
                output = bytes.fromhex(
                    self._trace_transaction[0]["result"]["output"][2:]
                )
            except JsonRpcError as e:
                # TODO make assertions about error.code?
                try:
                    self._fetch_debug_trace_transaction()
                    assert self._debug_trace_transaction is not None
                    output = bytes.fromhex(self._debug_trace_transaction["returnValue"])  # type: ignore
                except JsonRpcError as e:
                    # TODO make assertions about error.code?
                    raise RuntimeError(
                        f"Could not get return value for transaction {self.tx_hash} as trace_transaction and debug_trace_transaction are both unavailable"
                    )
        else:
            raise NotImplementedError

        if self._abi is None:
            return self._return_type(output)

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
    def gas_price(self) -> Wei:
        assert "gasPrice" in self._tx_params
        return Wei(self._tx_params["gasPrice"])

    @property
    def type(self) -> TransactionTypeEnum:
        return TransactionTypeEnum.LEGACY


class Eip2930Transaction(TransactionAbc[T]):
    @property
    def chain_id(self) -> int:
        assert "chainId" in self._tx_params
        return self._tx_params["chainId"]

    @property
    def access_list(self) -> Dict[Account, List[int]]:
        assert "accessList" in self._tx_params
        ret = {}
        for entry in self._tx_params["accessList"]:
            account = Account(entry[0])
            if account not in ret:
                ret[account] = []
            ret[account].append(entry[1])
        return ret

    @property
    def gas_price(self) -> Wei:
        assert "gasPrice" in self._tx_params
        return Wei(self._tx_params["gasPrice"])

    @property
    @_fetch_tx_data
    def y_parity(self) -> bool:
        return bool(int(self._tx_data["v"], 16) & 1)

    @property
    def type(self) -> TransactionTypeEnum:
        assert "type" in self._tx_params and self._tx_params["type"] == 1
        return TransactionTypeEnum.EIP2930


class Eip1559Transaction(TransactionAbc[T]):
    @property
    def chain_id(self) -> int:
        assert "chainId" in self._tx_params
        return self._tx_params["chainId"]

    @property
    def max_fee_per_gas(self) -> Wei:
        if "maxFeePerGas" not in self._tx_params:
            if self._tx_data is None:
                self._tx_data = self._chain.chain_interface.get_transaction(
                    self.tx_hash
                )
            return Wei(int(self._tx_data["maxFeePerGas"], 16))
        return Wei(self._tx_params["maxFeePerGas"])

    @property
    def max_priority_fee_per_gas(self) -> Wei:
        if "maxPriorityFeePerGas" not in self._tx_params:
            if self._tx_data is None:
                self._tx_data = self._chain.chain_interface.get_transaction(
                    self.tx_hash
                )
            return Wei(int(self._tx_data["maxPriorityFeePerGas"], 16))
        return Wei(self._tx_params["maxPriorityFeePerGas"])

    @property
    def access_list(self) -> Dict[Account, List[int]]:
        assert "accessList" in self._tx_params
        ret = {}
        for entry in self._tx_params["accessList"]:
            account = Account(entry[0])
            if account not in ret:
                ret[account] = []
            ret[account].append(entry[1])
        return ret

    @property
    @_fetch_tx_data
    def y_parity(self) -> bool:
        return bool(int(self._tx_data["v"], 16) & 1)

    @property
    def type(self) -> TransactionTypeEnum:
        assert "type" in self._tx_params and self._tx_params["type"] == 2
        return TransactionTypeEnum.EIP1559


@dataclass
class TransactionRevertedError(Exception):
    tx: Optional[TransactionAbc] = field(
        init=False, compare=False, default=None, repr=False
    )

    def __str__(self):
        s = ", ".join(
            [f"{f.name}={getattr(self, f.name)!r}" for f in fields(self) if f.init]
        )
        return f"{self.__class__.__qualname__}({s})"


@dataclass
class UnknownTransactionRevertedError(TransactionRevertedError):
    data: bytes


@dataclass
class Error(TransactionRevertedError):
    _abi = {
        "name": "Error",
        "type": "error",
        "inputs": [{"internalType": "string", "name": "message", "type": "string"}],
    }
    message: str


class PanicCodeEnum(IntEnum):
    GENERIC = 0
    "Generic compiler panic"
    ASSERT_FAIL = 1
    "Assert evaluated to false"
    UNDERFLOW_OVERFLOW = 0x11
    "Integer underflow or overflow"
    DIVISION_MODULO_BY_ZERO = 0x12
    "Division or modulo by zero"
    INVALID_CONVERSION_TO_ENUM = 0x21
    "Too big or negative integer for conversion to enum"
    ACCESS_TO_INCORRECTLY_ENCODED_STORAGE_BYTE_ARRAY = 0x22
    "Access to incorrectly encoded storage byte array"
    POP_EMPTY_ARRAY = 0x31
    ".pop() on empty array"
    INDEX_ACCESS_OUT_OF_BOUNDS = 0x32
    "Out-of-bounds or negative index access to fixed-length array"
    TOO_MUCH_MEMORY_ALLOCATED = 0x41
    "Too much memory allocated"
    INVALID_INTERNAL_FUNCTION_CALL = 0x51
    "Called invalid internal function"


@dataclass
class Panic(TransactionRevertedError):
    _abi = {
        "name": "Panic",
        "type": "error",
        "inputs": [{"internalType": "uint256", "name": "code", "type": "uint256"}],
    }
    code: "PanicCodeEnum"


class ExceptionWrapper:
    value: Optional[Exception] = None


@contextmanager
def must_revert(
    exceptions: Union[
        Exception, Type[Exception], Tuple[Union[Exception, Type[Exception]], ...]
    ] = TransactionRevertedError,
) -> AbstractContextManager[ExceptionWrapper]:
    if isinstance(exceptions, (tuple, list)):
        types = tuple(
            type(x) if not inspect.isclass(x) else x for x in exceptions
        )  # pyright: reportGeneralTypeIssues=false
    else:
        types = type(exceptions) if not inspect.isclass(exceptions) else exceptions

    wrapper = ExceptionWrapper()

    try:
        yield wrapper
        raise AssertionError(f"Expected revert of type {exceptions}")
    except types as e:  # pyright: reportGeneralTypeIssues=false
        wrapper.value = e

        if isinstance(exceptions, (tuple, list)):
            for ex, t in zip(
                exceptions, types
            ):  # pyright: reportGeneralTypeIssues=false
                if isinstance(ex, t) and not inspect.isclass(ex):
                    assert e == ex, f"Expected {ex} but got {e}"
                    return
        else:
            if not inspect.isclass(exceptions):
                assert e == exceptions, f"Expected {e} but got {exceptions}"


@contextmanager
def may_revert(
    exceptions: Union[
        Exception, Type[Exception], Tuple[Union[Exception, Type[Exception]], ...]
    ] = TransactionRevertedError,
) -> AbstractContextManager[ExceptionWrapper]:
    if isinstance(exceptions, (tuple, list)):
        types = tuple(type(x) if not inspect.isclass(x) else x for x in exceptions)
    else:
        types = type(exceptions) if not inspect.isclass(exceptions) else exceptions

    wrapper = ExceptionWrapper()

    try:
        yield wrapper
    except types as e:
        wrapper.value = e

        if isinstance(exceptions, (tuple, list)):
            for ex, t in zip(exceptions, types):
                if isinstance(ex, t) and not inspect.isclass(ex):
                    assert e == ex, f"Expected {ex} but got {e}"
                    return
        else:
            if not inspect.isclass(exceptions):
                assert e == exceptions, f"Expected {e} but got {exceptions}"
