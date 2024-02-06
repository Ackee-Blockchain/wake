from __future__ import annotations

import importlib
import reprlib
from collections import ChainMap
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional, Tuple, cast

import eth_abi
import eth_abi.abi
import eth_abi.exceptions
import eth_utils
from rich.console import Console
from rich.highlighter import ReprHighlighter
from rich.text import Text
from rich.tree import Tree

from wake.utils import StrEnum

from ..utils.formatters import format_wei
from . import hardhat_console
from .chain_interfaces import TxParams
from .core import (
    Account,
    Address,
    Chain,
    Contract,
    Wei,
    fix_library_abi,
    get_contracts_by_fqn,
    get_fqn_from_address,
    get_fqn_from_creation_code,
    process_debug_trace_for_fqn_overrides,
)
from .globals import get_config, get_verbosity
from .internal import read_from_memory
from .utils import get_contract_info_from_explorer

if TYPE_CHECKING:
    from .transactions import TransactionAbc


def get_precompiled_info(
    addr: Address, data: bytes
) -> Tuple[
    str, Optional[Tuple[Any, ...]], Optional[Tuple[Optional[str], ...]], List[str]
]:
    if addr == Address(1):
        if len(data) != 128:
            return "ecRecover", None, None, ["address"]
        return (
            "ecRecover",
            (data[:32], data[32:64], data[64:96], data[96:128]),
            ("hash", "v", "r", "s"),
            ["address"],
        )
    elif addr == Address(2):
        return "SHA2-256", (data,), ("data",), ["bytes32"]
    elif addr == Address(3):
        return "RIPEMD-160", (data,), ("data",), ["bytes32"]
    elif addr == Address(4):
        return "identity", (data,), ("data",), ["bytes"]
    elif addr == Address(5):
        if len(data) < 96:
            return "modexp", None, None, ["bytes"]
        base_length = int.from_bytes(data[:32], "big")
        exp_length = int.from_bytes(data[32:64], "big")
        mod_length = int.from_bytes(data[64:96], "big")
        return (
            "modexp",
            (
                base_length,
                exp_length,
                mod_length,
                data[96 : 96 + base_length],
                data[96 + base_length : 96 + base_length + exp_length],
                data[
                    96
                    + base_length
                    + exp_length : 96
                    + base_length
                    + exp_length
                    + mod_length
                ],
            ),
            ("Bsize", "Esize", "Msize", "B", "E", "M"),
            ["bytes"],
        )
    elif addr == Address(6):
        if len(data) != 128:
            return "ecAdd", None, None, ["bytes32", "bytes32"]
        x1 = int.from_bytes(data[:32], "big")
        y1 = int.from_bytes(data[32:64], "big")
        x2 = int.from_bytes(data[64:96], "big")
        y2 = int.from_bytes(data[96:128], "big")
        return (
            "ecAdd",
            (x1, y1, x2, y2),
            ("x1", "y1", "x2", "y2"),
            ["bytes32", "bytes32"],
        )
    elif addr == Address(7):
        if len(data) != 96:
            return "ecMul", None, None, ["bytes32", "bytes32"]
        x1 = int.from_bytes(data[:32], "big")
        y1 = int.from_bytes(data[32:64], "big")
        s = int.from_bytes(data[64:96], "big")
        return "ecMul", (x1, y1, s), ("x1", "y1", "s"), ["bytes32", "bytes32"]
    elif addr == Address(8):
        if len(data) % (6 * 32) != 0:
            return "ecPairing", None, None, ["bool"]
        coords = tuple(
            int.from_bytes(data[i : i + 32], "big") for i in range(0, len(data), 32)
        )
        names = tuple(
            f"y{i // 2 + 1}" if i % 2 else f"x{i // 2 + 1}" for i in range(len(coords))
        )
        return "ecPairing", coords, names, ["bool"]
    elif addr == Address(9):
        if len(data) != 4 + 64 + 128 + 16 + 1:
            return "Blake2F", None, None, ["bytes"]
        rounds = int.from_bytes(data[:4], "big")
        offset = 4
        h = tuple(
            int.from_bytes(data[i : i + 8], "little")
            for i in range(offset, offset + 8 * 8, 8)
        )
        offset += 8 * 8
        m = tuple(
            int.from_bytes(data[i : i + 8], "little")
            for i in range(offset, offset + 16 * 8, 8)
        )
        offset += 16 * 8
        t = tuple(
            int.from_bytes(data[i : i + 8], "little", signed=True)
            for i in range(offset, offset + 2 * 8, 8)
        )
        offset += 2 * 8
        f = data[offset]
        return (
            "Blake2F",
            (rounds, h, m, t, f),
            ("rounds", "h", "m", "t", "f"),
            ["bytes"],
        )
    else:
        raise ValueError(f"Unknown precompiled contract address: {addr}")


class CallTraceKind(StrEnum):
    CALL = "CALL"
    DELEGATECALL = "DELEGATECALL"
    STATICCALL = "STATICCALL"
    CALLCODE = "CALLCODE"
    CREATE = "CREATE"
    CREATE2 = "CREATE2"
    INTERNAL = "INTERNAL"  # unused


class CallTrace:
    _contract: Optional[Contract]
    _contract_name: Optional[str]
    _function_name: Optional[str]
    _selector: Optional[bytes]
    _function_is_special: bool
    _arguments: Optional[List]
    _argument_names: Optional[List[Optional[str]]]
    _status: bool
    _gas: int
    _value: Wei
    _kind: CallTraceKind
    _depth: int
    _origin: Account
    _chain: Chain
    _subtraces: List[CallTrace]
    _parent: Optional[CallTrace]
    _address: Optional[Address]
    _output_types: List[str]
    _error_name: Optional[str]
    _error_arguments: Optional[List]
    _revert_data: Optional[bytes]
    _return_value: Optional[List]
    _abi: Dict[bytes, Any]

    def __init__(
        self,
        contract: Optional[Contract],
        contract_name: Optional[str],
        function_name: Optional[str],
        selector: Optional[bytes],
        address: Optional[Address],
        arguments: Optional[Iterable],
        argument_names: Optional[Iterable[Optional[str]]],
        gas: int,
        value: int,
        kind: CallTraceKind,
        depth: int,
        chain: Chain,
        origin: Account,
        output_types: List[str],
        abi: Dict[bytes, Any],
        function_is_special: bool = False,
    ):
        self._contract = contract
        self._contract_name = contract_name
        self._function_name = function_name
        self._selector = selector
        self._address = address
        self._arguments = list(arguments) if arguments is not None else None
        self._argument_names = (
            list(argument_names) if argument_names is not None else None
        )
        self._gas = gas
        self._value = Wei(value)
        self._kind = kind
        self._depth = depth
        self._chain = chain
        self._origin = origin
        self._output_types = output_types
        self._function_is_special = function_is_special
        self._status = True
        self._subtraces = []
        self._parent = None
        self._error_name = None
        self._error_arguments = None
        self._revert_data = None
        self._return_value = None
        self._abi = abi
        self._abi[bytes.fromhex("08c379a0")] = {
            "name": "Error",
            "type": "error",
            "inputs": [{"internalType": "string", "name": "message", "type": "string"}],
        }
        self._abi[bytes.fromhex("4e487b71")] = {
            "name": "Panic",
            "type": "error",
            "inputs": [{"internalType": "uint256", "name": "code", "type": "uint256"}],
        }

    def __str__(self):
        console = Console()
        with console.capture() as capture:
            console.print(self)
        return capture.get()

    __repr__ = __str__

    def __rich__(self):
        tree = Tree(self._get_label())
        self._into_tree(tree)
        return tree

    def _into_tree(self, tree: Tree):
        for subtrace in self._subtraces:
            t = tree.add(subtrace._get_label())
            subtrace._into_tree(t)

    def _get_label(self) -> Text:
        options = get_config().general.call_trace_options
        ret = Text()

        if "contract_name" in options:
            ret.append_text(
                Text.from_markup(
                    f"[bright_magenta]{self.contract_name or 'Unknown'}[/bright_magenta]"
                )
            )

        if "address" in options:
            label = None
            if self.address is not None:
                label = Account(self.address, self.chain).label

            if "contract_name" in options:
                ret.append_text(
                    Text.from_markup(f"([blue]{label or self.address}[/blue])")
                )
            else:
                ret.append_text(
                    Text.from_markup(f"[blue]{label or self.address}[/blue]")
                )

        if "function_name" in options:
            if "contract_name" in options or "address" in options:
                ret.append(".")

            if self.function_is_special:
                ret.append_text(
                    Text.from_markup(
                        f"<[bright_magenta]{self.function_name or '???'}[/bright_magenta]>"
                    )
                )
            else:
                ret.append_text(
                    Text.from_markup(
                        f"[bright_magenta]{self.function_name or '???'}[/bright_magenta]"
                    )
                )

        arg_repr = reprlib.Repr()
        arg_repr.maxstring = 64
        arg_repr.maxother = 44

        if "named_arguments" in options:
            if self.arguments is not None:
                assert self.argument_names is not None
                ret.append("(")
                for i, (arg, arg_name) in enumerate(
                    zip(self.arguments, self.argument_names)
                ):
                    if get_verbosity() > 0:
                        r = repr(arg)
                    else:
                        r = arg_repr.repr(arg)

                    if arg_name is not None and len(arg_name.strip()) > 0:
                        t = Text(f"{arg_name.strip()}={r}")
                    else:
                        t = Text(r)
                    ReprHighlighter().highlight(t)
                    ret.append_text(t)
                    if i < len(self.arguments) - 1:
                        ret.append(", ")
                ret.append(")")
            else:
                ret.append("(???)")
        elif "arguments" in options:
            if self.arguments is not None:
                ret.append("(")
                for i, arg in enumerate(self.arguments):
                    if get_verbosity() > 0:
                        t = Text(repr(arg))
                    else:
                        t = Text(arg_repr.repr(arg))
                    ReprHighlighter().highlight(t)
                    ret.append_text(t)
                    if i < len(self.arguments) - 1:
                        ret.append(", ")
                ret.append(")")
            else:
                ret.append("(???)")

        if "status" in options:
            ret.append_text(
                Text.from_markup(
                    f" {'[green]✓[/green]' if self.status else '[red]✗[/red]'}"
                )
            )

        if "call_type" in options:
            if self.kind != CallTraceKind.CALL:
                ret.append_text(
                    Text.from_markup(
                        f" [yellow]\[{self.kind}][/yellow]"  # pyright: ignore reportInvalidStringEscapeSequence
                    )
                )

        if "value" in options and self.value > 0:
            ret.append_text(
                Text.from_markup(
                    f" [sea_green2]\[{format_wei(self.value)}][/sea_green2]"  # pyright: ignore reportInvalidStringEscapeSequence
                )
            )

        if "gas" in options:
            ret.append_text(
                Text.from_markup(
                    f" [cyan]\[{self.gas:,} gas][/cyan]"  # pyright: ignore reportInvalidStringEscapeSequence
                )
            )

        if "sender" in options:
            sender = self.sender
            if sender is not None:
                ret.append_text(
                    Text.from_markup(
                        f" [blue_violet]\[{sender} sender][/blue_violet]"  # pyright: ignore reportInvalidStringEscapeSequence
                    )
                )

        if "return_value" in options:
            if self._return_value is not None and len(self._return_value) > 0:
                ret.append("\n➞ ")
                for i, arg in enumerate(self._return_value):
                    t = Text(repr(arg))
                    ReprHighlighter().highlight(t)
                    ret.append_text(t)
                    if i < len(self._return_value) - 1:
                        ret.append(", ")

        if "error" in options:
            if self._error_name is not None:
                ret.append("\n➞ ")
                ret.append_text(Text.from_markup(f"[red]{self._error_name}[/red]("))
                for i, arg in enumerate(self.error_arguments or []):
                    t = Text(repr(arg))
                    ReprHighlighter().highlight(t)
                    ret.append_text(t)
                    if i < len(self.error_arguments or []) - 1:
                        ret.append(", ")
                ret.append(")")

        return ret

    @property
    def subtraces(self) -> Tuple[CallTrace, ...]:
        return tuple(self._subtraces)

    @property
    def parent(self) -> Optional[CallTrace]:
        return self._parent

    @property
    def contract(self) -> Optional[Contract]:
        return self._contract

    @property
    def contract_name(self) -> Optional[str]:
        return self._contract_name

    @property
    def function_name(self) -> Optional[str]:
        return self._function_name

    @property
    def function_is_special(self) -> bool:
        return self._function_is_special

    @property
    def address(self) -> Optional[Address]:
        return self._address

    @property
    def arguments(self) -> Optional[Tuple]:
        if self._arguments is None:
            return None
        return tuple(self._arguments)

    @property
    def argument_names(self) -> Optional[Tuple[Optional[str], ...]]:
        if self._argument_names is None:
            return None
        return tuple(self._argument_names)

    @property
    def status(self) -> bool:
        return self._status

    @property
    def value(self) -> Wei:
        return self._value

    @property
    def kind(self) -> CallTraceKind:
        return self._kind

    @property
    def depth(self) -> int:
        return self._depth

    @property
    def sender(self) -> Optional[Account]:
        current_trace = self
        while (
            current_trace is not None
            and current_trace.kind == CallTraceKind.DELEGATECALL
        ):
            current_trace = current_trace.parent

        if current_trace is None or current_trace.parent is None:
            return self._origin

        if current_trace.parent.address is not None:
            return Account(current_trace.parent.address, current_trace.parent.chain)
        return None

    @property
    def chain(self) -> Chain:
        return self._chain

    @property
    def gas(self) -> int:
        return self._gas

    @property
    def error_name(self) -> Optional[str]:
        return self._error_name

    @property
    def error_arguments(self) -> Optional[Tuple]:
        if self._error_arguments is None:
            return None
        return tuple(self._error_arguments)

    @property
    def return_value(self) -> Optional[List]:
        return self._return_value

    @classmethod
    def from_debug_trace(
        cls,
        tx: TransactionAbc,
        trace: Dict[str, Any],
        tx_params: TxParams,
        gas_limit: int,
    ):
        from .transactions import PanicCodeEnum

        fqn_overrides: ChainMap[Address, Optional[str]] = ChainMap()

        # process fqn_overrides for all txs before this one in the same block
        for i in range(tx.tx_index):
            tx_before = tx.block.txs[i]
            tx_before._fetch_debug_trace_transaction()
            process_debug_trace_for_fqn_overrides(
                tx_before,
                tx_before._debug_trace_transaction,  # pyright: ignore reportGeneralTypeIssues
                fqn_overrides,
            )

        assert len(fqn_overrides.maps) == 1

        if tx.to is None:
            try:
                origin_fqn, _ = get_fqn_from_creation_code(tx.data)
            except ValueError:
                origin_fqn = None
        else:
            if tx.to.address in fqn_overrides:
                origin_fqn = fqn_overrides[tx.to.address]
            else:
                origin_fqn = get_fqn_from_address(
                    tx.to.address, tx.block.number - 1, tx.chain
                )

        contracts = [origin_fqn]
        values = [0 if "value" not in tx_params else tx_params["value"]]
        assert "from" in tx_params
        origin = Account(tx_params["from"], tx.chain)

        contracts_by_fqn = get_contracts_by_fqn()

        if "value" not in tx_params:
            value = 0
        else:
            value = tx_params["value"]

        explorer_info = None
        precompiled_info = None
        if (
            origin_fqn is None or origin_fqn not in contracts_by_fqn
        ) and tx.to is not None:
            if Address(0) < tx.to.address <= Address(9):
                precompiled_info = get_precompiled_info(
                    tx.to.address, b"" if "data" not in tx_params else tx_params["data"]
                )
            elif tx.chain._fork is not None:
                explorer_info = get_contract_info_from_explorer(
                    tx.to.address, tx.chain.chain_id
                )

        if (
            (origin_fqn is None or origin_fqn not in contracts_by_fqn)
            and explorer_info is None
            and precompiled_info is None
        ):
            root_trace = CallTrace(
                None,
                None,
                None,
                None,
                None if tx.to is None else tx.to.address,
                [b"" if "data" not in tx_params else tx_params["data"]],
                [None],
                gas_limit,
                value,
                CallTraceKind.CALL,
                1,
                tx.chain,
                origin,
                [],
                {},
                True,
            )
        elif precompiled_info is not None:
            assert tx.to is not None
            precompiled_name, args, arg_names, output_types = precompiled_info
            root_trace = CallTrace(
                None,
                "<precompiled>",
                precompiled_name,
                None,
                tx.to.address,
                args,
                arg_names,
                gas_limit,
                value,
                CallTraceKind.CALL,
                1,
                tx.chain,
                origin,
                output_types,
                {},
                False,
            )
        else:
            if explorer_info is not None:
                contract_name, contract_abi = explorer_info
                obj = None
            else:
                assert origin_fqn is not None
                contract_name = origin_fqn.split(":")[-1]
                module_name, attrs = contracts_by_fqn[origin_fqn]
                obj = getattr(importlib.import_module(module_name), attrs[0])
                for attr in attrs[1:]:
                    obj = getattr(obj, attr)
                contract_abi = obj._abi

            if tx.to is None:
                if "data" not in tx_params or "constructor" not in contract_abi:
                    args = []
                    arg_names = []
                else:
                    _, constructor_offset = get_fqn_from_creation_code(
                        tx_params["data"]
                    )
                    fn_abi = contract_abi["constructor"]
                    input_types = [
                        eth_utils.abi.collapse_if_tuple(cast(Dict[str, Any], arg))
                        for arg in fix_library_abi(fn_abi["inputs"])
                    ]
                    try:
                        args = list(
                            eth_abi.abi.decode(
                                input_types, tx_params["data"][constructor_offset:]
                            )
                        )
                        arg_names = [arg["name"] for arg in fn_abi["inputs"]]
                        for i, type in enumerate(input_types):
                            if type == "address":
                                args[i] = Account(Address(args[i]), tx.chain)
                    except Exception:
                        args = None
                        arg_names = None
                root_trace = CallTrace(
                    obj,
                    contract_name,
                    "constructor",
                    None,
                    tx.return_value.address if tx.status == 1 else None,
                    args,
                    arg_names,
                    gas_limit,
                    value,
                    CallTraceKind.CREATE,
                    1,
                    tx.chain,
                    origin,
                    [],
                    contract_abi,
                    True,
                )
            elif (
                "data" not in tx_params
                or len(tx_params["data"]) == 0
                and "receive" in contract_abi
            ):
                root_trace = CallTrace(
                    obj,
                    contract_name,
                    "receive",
                    None,
                    tx.to.address,
                    [],
                    [],
                    gas_limit,
                    value,
                    CallTraceKind.CALL,
                    1,
                    tx.chain,
                    origin,
                    [],
                    contract_abi,
                    True,
                )
            elif (
                "data" not in tx_params
                or len(tx_params["data"]) < 4
                or tx_params["data"][:4] not in contract_abi
            ):
                if "fallback" in contract_abi and (
                    value == 0
                    or contract_abi["fallback"]["stateMutability"] == "payable"
                ):
                    root_trace = CallTrace(
                        obj,
                        contract_name,
                        "fallback",
                        None,
                        tx.to.address,
                        [b"" if "data" not in tx_params else tx_params["data"]],
                        [None],
                        gas_limit,
                        value,
                        CallTraceKind.CALL,
                        1,
                        tx.chain,
                        origin,
                        [],
                        contract_abi,
                        True,
                    )
                else:
                    root_trace = CallTrace(
                        obj,
                        contract_name,
                        None,
                        None,
                        tx.to.address,
                        [b"" if "data" not in tx_params else tx_params["data"]],
                        [None],
                        gas_limit,
                        value,
                        CallTraceKind.CALL,
                        1,
                        tx.chain,
                        origin,
                        [],
                        contract_abi,
                        True,
                    )
            else:
                fn_abi = contract_abi[tx_params["data"][:4]]
                input_types = [
                    eth_utils.abi.collapse_if_tuple(cast(Dict[str, Any], arg))
                    for arg in fix_library_abi(fn_abi["inputs"])
                ]
                output_types = (
                    [
                        eth_utils.abi.collapse_if_tuple(cast(Dict[str, Any], arg))
                        for arg in fix_library_abi(fn_abi["outputs"])
                    ]
                    if "outputs" in fn_abi
                    else []
                )
                try:
                    args = list(eth_abi.abi.decode(input_types, tx_params["data"][4:]))
                    arg_names = [arg["name"] for arg in fn_abi["inputs"]]
                    for i, type in enumerate(input_types):
                        if type == "address":
                            args[i] = Account(Address(args[i]), tx.chain)
                except Exception:
                    args = None
                    arg_names = None
                root_trace = CallTrace(
                    obj,
                    contract_name,
                    fn_abi["name"],
                    tx_params["data"][:4],
                    tx.to.address,
                    args,
                    arg_names,
                    gas_limit,
                    value,
                    CallTraceKind.CALL,
                    1,
                    tx.chain,
                    origin,
                    output_types,
                    contract_abi,
                )

        current_trace = root_trace

        for i, log in enumerate(trace["structLogs"]):
            assert current_trace is not None
            if current_trace.depth != log["depth"]:
                prev_op = trace["structLogs"][i - 1]["op"]
                if prev_op in {
                    "CALL",
                    "CALLCODE",
                    "DELEGATECALL",
                    "STATICCALL",
                }:
                    # precompiled contract was called in the previous step
                    assert current_trace is not None

                    status = int(log["stack"][-1], 16) != 0
                    if prev_op in {"CALL", "CALLCODE"}:
                        ret_offset = int(trace["structLogs"][i - 1]["stack"][-6], 16)
                        ret_size = int(trace["structLogs"][i - 1]["stack"][-7], 16)
                    else:
                        ret_offset = int(trace["structLogs"][i - 1]["stack"][-5], 16)
                        ret_size = int(trace["structLogs"][i - 1]["stack"][-6], 16)

                    data = bytes(read_from_memory(ret_offset, ret_size, log["memory"]))

                    output_types = current_trace._output_types
                    try:
                        return_value = list(eth_abi.abi.decode(output_types, data))
                        for j, type in enumerate(output_types):
                            if type == "address":
                                return_value[j] = Account(
                                    Address(return_value[j]), tx.chain
                                )
                    except Exception:
                        return_value = [data]

                    current_trace._return_value = return_value
                    current_trace._status = status

                    current_trace = current_trace._parent
                    fqn_overrides.maps[1].update(fqn_overrides.maps[0])
                    fqn_overrides.maps.pop(0)
                    contracts.pop()
                    values.pop()
                else:
                    # the depth may not be equal in case of out-of-gas
                    assert current_trace is not None
                    assert current_trace.depth >= log["depth"]
                    while current_trace.depth > log["depth"]:
                        current_trace._error_name = "UnknownTransactionRevertedError"
                        current_trace._error_arguments = [b""]
                        current_trace._revert_data = b""

                        if len(fqn_overrides.maps) > 1:
                            fqn_overrides.maps[1].update(fqn_overrides.maps[0])
                        fqn_overrides.maps.pop(0)

                        current_trace._status = False
                        current_trace = current_trace._parent
                        assert current_trace is not None
                        contracts.pop()
                        values.pop()

            if log["op"] in {"CALL", "CALLCODE", "DELEGATECALL", "STATICCALL"}:
                if log["op"] in {"CALL", "CALLCODE"}:
                    gas = int(log["stack"][-1], 16)
                    value = int(log["stack"][-3], 16)
                    args_offset = int(log["stack"][-4], 16)
                    args_size = int(log["stack"][-5], 16)
                elif log["op"] == "DELEGATECALL":
                    gas = int(log["stack"][-1], 16)
                    value = values[-1]
                    args_offset = int(log["stack"][-3], 16)
                    args_size = int(log["stack"][-4], 16)
                else:
                    gas = int(log["stack"][-1], 16)
                    value = 0
                    args_offset = int(log["stack"][-3], 16)
                    args_size = int(log["stack"][-4], 16)

                data = bytes(read_from_memory(args_offset, args_size, log["memory"]))

                assert current_trace is not None

                addr = Address(int(log["stack"][-2], 16))
                if addr in fqn_overrides:
                    fqn = fqn_overrides[addr]
                else:
                    fqn = get_fqn_from_address(addr, tx.block.number - 1, tx.chain)

                explorer_info = None
                precompiled_info = None
                if fqn is None and addr != Address(
                    "0x000000000000000000636F6e736F6c652e6c6f67"
                ):
                    if Address(0) < addr <= Address(9):
                        precompiled_info = get_precompiled_info(addr, data)
                    elif tx.chain._fork is not None:
                        explorer_info = get_contract_info_from_explorer(
                            addr, tx.chain.chain_id
                        )

                if fqn is None and explorer_info is None and precompiled_info is None:
                    if addr == Address("0x000000000000000000636F6e736F6c652e6c6f67"):
                        if data[:4] in hardhat_console.abis:
                            fn_abi = hardhat_console.abis[data[:4]]
                            input_types = [
                                eth_utils.abi.collapse_if_tuple(
                                    cast(Dict[str, Any], arg)
                                )
                                for arg in fix_library_abi(fn_abi)
                            ]
                            try:
                                args = list(eth_abi.abi.decode(input_types, data[4:]))
                                arg_names = [arg["name"] for arg in fn_abi]
                                for j, type in enumerate(input_types):
                                    if type == "address":
                                        args[j] = Account(Address(args[j]), tx.chain)
                            except Exception:
                                args = None
                                arg_names = None
                        else:
                            args = [data]
                            arg_names = [None]

                        call_trace = CallTrace(
                            None,
                            "console",
                            "log",
                            data[:4],
                            addr,
                            args,
                            arg_names,
                            gas,
                            value,
                            log["op"],
                            current_trace.depth + 1,
                            tx.chain,
                            origin,
                            [],
                            {},
                        )
                    else:
                        call_trace = CallTrace(
                            None,
                            None,
                            None,
                            None,
                            addr,
                            [data],
                            [None],
                            gas,
                            value,
                            log["op"],
                            current_trace.depth + 1,
                            tx.chain,
                            origin,
                            [],
                            {},
                            True,
                        )
                elif precompiled_info is not None:
                    call_trace = CallTrace(
                        None,
                        "<precompiled>",
                        precompiled_info[0],
                        None,
                        addr,
                        precompiled_info[1],
                        precompiled_info[2],
                        gas,
                        value,
                        log["op"],
                        current_trace.depth + 1,
                        tx.chain,
                        origin,
                        precompiled_info[3],
                        {},
                        False,
                    )
                else:
                    if explorer_info is not None:
                        contract_name, contract_abi = explorer_info
                        obj = None
                    else:
                        assert fqn is not None
                        contract_name = fqn.split(":")[-1]
                        module_name, attrs = contracts_by_fqn[fqn]
                        obj = getattr(importlib.import_module(module_name), attrs[0])
                        for attr in attrs[1:]:
                            obj = getattr(obj, attr)
                        contract_abi = obj._abi

                    if args_size >= 4:
                        selector = data[:4]
                        if selector in contract_abi:
                            fn_abi = contract_abi[selector]
                            input_types = [
                                eth_utils.abi.collapse_if_tuple(
                                    cast(Dict[str, Any], arg)
                                )
                                for arg in fix_library_abi(fn_abi["inputs"])
                            ]
                            output_types = (
                                [
                                    eth_utils.abi.collapse_if_tuple(
                                        cast(Dict[str, Any], arg)
                                    )
                                    for arg in fix_library_abi(fn_abi["outputs"])
                                ]
                                if "outputs" in fn_abi
                                else []
                            )
                            try:
                                args = list(eth_abi.abi.decode(input_types, data[4:]))
                                arg_names = [arg["name"] for arg in fn_abi["inputs"]]
                                for j, type in enumerate(input_types):
                                    if type == "address":
                                        args[j] = Account(Address(args[j]), tx.chain)
                            except Exception:
                                args = None
                                arg_names = None
                            fn_name = fn_abi["name"]
                            is_special = False
                        elif "fallback" in contract_abi and (
                            value == 0
                            or contract_abi["fallback"]["stateMutability"] == "payable"
                        ):
                            selector = None
                            fn_name = "fallback"
                            args = [data]
                            arg_names = [None]
                            output_types = []
                            is_special = True
                        else:
                            selector = None
                            fn_name = None
                            args = [data]
                            arg_names = [None]
                            output_types = []
                            is_special = True
                    else:
                        selector = None
                        output_types = []
                        if args_size == 0 and "receive" in contract_abi:
                            fn_name = "receive"
                            args = []
                            arg_names = []
                            is_special = True
                        elif "fallback" in contract_abi and (
                            value == 0
                            or contract_abi["fallback"]["stateMutability"] == "payable"
                        ):
                            fn_name = "fallback"
                            args = [data]
                            arg_names = [None]
                            is_special = True
                        else:
                            fn_name = None
                            args = [data]
                            arg_names = [None]
                            is_special = True

                    call_trace = CallTrace(
                        obj,
                        contract_name,
                        fn_name,
                        selector,
                        addr,
                        args,
                        arg_names,
                        gas,
                        value,
                        log["op"],
                        current_trace.depth + 1,
                        tx.chain,
                        origin,
                        output_types,
                        contract_abi,
                        is_special,
                    )

                current_trace._subtraces.append(call_trace)
                call_trace._parent = current_trace
                current_trace = call_trace
                contracts.append(fqn)
                values.append(value)
                fqn_overrides.maps.insert(0, {})
            elif log["op"] in {"INVALID", "RETURN", "REVERT", "STOP", "SELFDESTRUCT"}:
                if log["op"] in {"INVALID", "REVERT"}:
                    status = False
                else:
                    status = True

                assert current_trace is not None
                while current_trace._kind == CallTraceKind.INTERNAL:
                    current_trace._status = status
                    current_trace = current_trace._parent
                    assert current_trace is not None

                if log["op"] == "INVALID":
                    current_trace._error_name = "UnknownTransactionRevertedError"
                    current_trace._error_arguments = [b""]
                elif log["op"] == "RETURN":
                    data_offset = int(log["stack"][-1], 16)
                    data_size = int(log["stack"][-2], 16)
                    data = bytes(
                        read_from_memory(data_offset, data_size, log["memory"])
                    )

                    output_types = current_trace._output_types
                    try:
                        return_value = list(eth_abi.abi.decode(output_types, data))
                        for j, type in enumerate(output_types):
                            if type == "address":
                                return_value[j] = Account(
                                    Address(return_value[j]), tx.chain
                                )
                    except Exception:
                        return_value = [data]

                    current_trace._return_value = return_value
                elif log["op"] == "REVERT":
                    data_offset = int(log["stack"][-1], 16)
                    data_size = int(log["stack"][-2], 16)
                    data = bytes(
                        read_from_memory(data_offset, data_size, log["memory"])
                    )
                    current_trace._revert_data = data

                    if any(t._revert_data == data for t in current_trace._subtraces):
                        # error propagated from a subtrace
                        subtrace = next(
                            t
                            for t in current_trace._subtraces
                            if t._revert_data == data
                        )
                        current_trace._error_name = subtrace._error_name
                        current_trace._error_arguments = subtrace._error_arguments
                    elif len(data) < 4 or data[:4] not in current_trace._abi:
                        current_trace._error_name = "UnknownTransactionRevertedError"
                        current_trace._error_arguments = [data]
                    else:
                        try:
                            error_types = [
                                eth_utils.abi.collapse_if_tuple(
                                    cast(Dict[str, Any], arg)
                                )
                                for arg in current_trace._abi[data[:4]]["inputs"]
                            ]
                            error_args = list(eth_abi.abi.decode(error_types, data[4:]))
                            for j, type in enumerate(error_types):
                                if type == "address":
                                    error_args[j] = Account(
                                        Address(error_args[j]), tx.chain
                                    )
                            current_trace._error_name = current_trace._abi[data[:4]][
                                "name"
                            ]
                            if data[:4] == bytes.fromhex("4e487b71"):
                                # convert Panic int to enum
                                error_args[0] = PanicCodeEnum(error_args[0])
                            current_trace._error_arguments = error_args
                        except Exception:
                            current_trace._error_name = (
                                "UnknownTransactionRevertedError"
                            )
                            current_trace._error_arguments = [data]
                else:
                    output_types = current_trace._output_types
                    return_value = list(
                        eth_abi.abi.decode(
                            output_types, b"\x00" * 32 * len(output_types)
                        )
                    )
                    for j, type in enumerate(output_types):
                        if type == "address":
                            return_value[j] = Account(
                                Address(return_value[j]), tx.chain
                            )
                    current_trace._return_value = return_value

                assert current_trace is not None
                if (
                    log["op"] not in {"INVALID", "REVERT"}
                    and len(fqn_overrides.maps) > 1
                ):
                    fqn_overrides.maps[1].update(fqn_overrides.maps[0])
                fqn_overrides.maps.pop(0)

                if current_trace.kind in {CallTraceKind.CREATE, CallTraceKind.CREATE2}:
                    try:
                        address = Address(
                            int(trace["structLogs"][i + 1]["stack"][-1], 16)
                        )
                        if address != Address(0):
                            current_trace._address = address
                            fqn_overrides.maps[0][address] = contracts[-1]
                    except IndexError:
                        pass

                current_trace._status = status
                current_trace = current_trace._parent

                contracts.pop()
                values.pop()
            elif log["op"] in {"CREATE", "CREATE2"}:
                gas = trace["structLogs"][i + 1]["gas"]  # TODO is this correct?
                value = int(log["stack"][-1], 16)
                offset = int(log["stack"][-2], 16)
                length = int(log["stack"][-3], 16)

                creation_code = read_from_memory(offset, length, log["memory"])
                contract_abi = {}
                try:
                    fqn, constructor_offset = get_fqn_from_creation_code(creation_code)

                    contract_name = fqn.split(":")[-1]
                    module_name, attrs = contracts_by_fqn[fqn]
                    obj = getattr(importlib.import_module(module_name), attrs[0])
                    for attr in attrs[1:]:
                        obj = getattr(obj, attr)
                    contract_abi = obj._abi

                    if "constructor" not in contract_abi:
                        args = []
                        arg_names = []
                    else:
                        fn_abi = contract_abi["constructor"]
                        input_types = [
                            eth_utils.abi.collapse_if_tuple(cast(Dict[str, Any], arg))
                            for arg in fix_library_abi(fn_abi["inputs"])
                        ]
                        try:
                            args = list(
                                eth_abi.abi.decode(
                                    input_types, creation_code[constructor_offset:]
                                )
                            )
                            arg_names = [arg["name"] for arg in fn_abi["inputs"]]
                            for j, type in enumerate(input_types):
                                if type == "address":
                                    args[j] = Account(Address(args[j]), tx.chain)
                        except Exception:
                            args = None
                            arg_names = None
                except ValueError:
                    fqn = None
                    obj = None
                    contract_name = None
                    args = []
                    arg_names = []

                assert current_trace is not None
                call_trace = CallTrace(
                    obj,
                    contract_name,
                    "constructor",
                    None,
                    None,  # to be set later
                    args,
                    arg_names,
                    gas,
                    value,
                    log["op"],
                    current_trace.depth + 1,
                    tx.chain,
                    origin,
                    [],
                    contract_abi,
                    True,
                )

                current_trace._subtraces.append(call_trace)
                call_trace._parent = current_trace
                current_trace = call_trace
                contracts.append(fqn)
                values.append(value)
                fqn_overrides.maps.insert(0, {})

        return root_trace
