from __future__ import annotations

import importlib
import reprlib
from collections import ChainMap
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, cast

import eth_abi
import eth_abi.exceptions
import eth_utils
from rich.console import Console
from rich.highlighter import ReprHighlighter
from rich.text import Text
from rich.tree import Tree

from woke.utils import StrEnum

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
from .internal import read_from_memory
from .utils import get_contract_info_from_explorer

if TYPE_CHECKING:
    from .transactions import TransactionAbc


def get_precompiled_info(
    addr: Address, data: bytes
) -> Tuple[str, Optional[Tuple[Any, ...]]]:
    if addr == Address(1):
        if len(data) != 128:
            return "ecRecover", None
        return "ecRecover", (data[:32], data[32:64], data[64:96], data[96:128])
    elif addr == Address(2):
        return "SHA2-256", (data,)
    elif addr == Address(3):
        return "RIPEMD-160", (data,)
    elif addr == Address(4):
        return "identity", (data,)
    elif addr == Address(5):
        if len(data) < 96:
            return "modexp", None
        base_length = int.from_bytes(data[:32], "big")
        exp_length = int.from_bytes(data[32:64], "big")
        mod_length = int.from_bytes(data[64:96], "big")
        return "modexp", (
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
        )
    elif addr == Address(6):
        if len(data) != 128:
            return "ecAdd", None
        x1 = int.from_bytes(data[:32], "big")
        y1 = int.from_bytes(data[32:64], "big")
        x2 = int.from_bytes(data[64:96], "big")
        y2 = int.from_bytes(data[96:128], "big")
        return "ecAdd", (x1, y1, x2, y2)
    elif addr == Address(7):
        if len(data) != 96:
            return "ecMul", None
        x1 = int.from_bytes(data[:32], "big")
        y1 = int.from_bytes(data[32:64], "big")
        s = int.from_bytes(data[64:96], "big")
        return "ecMul", (x1, y1, s)
    elif addr == Address(8):
        if len(data) % (6 * 32) != 0:
            return "ecPairing", None
        coords = tuple(
            int.from_bytes(data[i : i + 32], "big") for i in range(0, len(data), 32)
        )
        return "ecPairing", coords
    elif addr == Address(9):
        if len(data) != 4 + 64 + 128 + 16 + 1:
            return "Blake2F", None
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
        return "Blake2F", (rounds, h, m, t, f)
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
    _status: bool
    _value: Wei
    _kind: CallTraceKind
    _depth: int
    _chain: Chain
    _subtraces: List[CallTrace]
    _parent: Optional[CallTrace]
    _address: Optional[Address]

    def __init__(
        self,
        contract: Optional[Contract],
        contract_name: Optional[str],
        function_name: Optional[str],
        selector: Optional[bytes],
        address: Optional[Address],
        arguments: Optional[List],
        value: int,
        kind: CallTraceKind,
        depth: int,
        chain: Chain,
        function_is_special: bool = False,
    ):
        self._contract = contract
        self._contract_name = contract_name
        self._function_name = function_name
        self._selector = selector
        self._address = address
        self._arguments = arguments
        self._value = Wei(value)
        self._kind = kind
        self._depth = depth
        self._chain = chain
        self._function_is_special = function_is_special
        self._status = True
        self._subtraces = []
        self._parent = None

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
        ret = Text()

        label = None
        if self.address is not None:
            label = Account(self.address, self.chain).label

        if label is not None:
            contract_name = label
        elif self.contract_name is not None:
            contract_name = self.contract_name
        else:
            contract_name = f"Unknown({self.address})"

        ret.append_text(
            Text.from_markup(f"[bright_magenta]{contract_name}[/bright_magenta].")
        )

        if self.function_name is not None:
            function_name = self.function_name
        else:
            function_name = "???"

        if self.function_is_special:
            ret.append_text(
                Text.from_markup(f"<[bright_magenta]{function_name}[/bright_magenta]>")
            )
        else:
            ret.append_text(
                Text.from_markup(
                    f"[bright_magenta]{self.function_name}[/bright_magenta]"
                )
            )

        if self.kind != CallTraceKind.INTERNAL:
            if self.arguments is not None:
                ret.append("(")
                for i, arg in enumerate(self.arguments):
                    t = Text(reprlib.repr(arg))
                    ReprHighlighter().highlight(t)
                    ret.append_text(t)
                    if i < len(self.arguments) - 1:
                        ret.append(", ")
                ret.append(")")
            else:
                ret.append("(???)")

        ret.append_text(
            Text.from_markup(
                f" {'[green]✓[/green]' if self.status else '[red]✗[/red]'}"
            )
        )

        if self.kind != CallTraceKind.CALL:
            ret.append_text(
                Text.from_markup(f" [yellow]\[{self.kind}][/yellow]")
            )  # pyright: reportInvalidStringEscapeSequence=false

        return ret

    @property
    def subtraces(self) -> Tuple[CallTrace, ...]:
        return tuple(self._subtraces)

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
    def chain(self) -> Chain:
        return self._chain

    @classmethod
    def from_debug_trace(
        cls,
        tx: TransactionAbc,
        trace: Dict[str, Any],
        tx_params: TxParams,
    ):
        fqn_overrides: ChainMap[Address, Optional[str]] = ChainMap()

        # process fqn_overrides for all txs before this one in the same block
        for i in range(tx.tx_index):
            tx_before = tx.block.txs[i]
            tx_before._fetch_debug_trace_transaction()
            process_debug_trace_for_fqn_overrides(
                tx_before, tx_before._debug_trace_transaction, fqn_overrides
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
            if tx.to.address <= Address(9):
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
                value,
                CallTraceKind.CALL,
                1,
                tx.chain,
                True,
            )
        elif precompiled_info is not None:
            assert tx.to is not None
            precompiled_name, args = precompiled_info
            root_trace = CallTrace(
                None,
                "<precompiled>",
                precompiled_name,
                None,
                tx.to.address,
                args,
                value,
                CallTraceKind.CALL,
                1,
                tx.chain,
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
                else:
                    _, constructor_offset = get_fqn_from_creation_code(
                        tx_params["data"]
                    )
                    fn_abi = contract_abi["constructor"]
                    output_types = [
                        eth_utils.abi.collapse_if_tuple(cast(Dict[str, Any], arg))
                        for arg in fix_library_abi(fn_abi["inputs"])
                    ]
                    try:
                        args = list(
                            eth_abi.abi.decode(
                                output_types, tx_params["data"][constructor_offset:]
                            )
                        )  # pyright: reportGeneralTypeIssues=false
                    except eth_abi.exceptions.DecodingError:
                        args = None
                root_trace = CallTrace(
                    obj,
                    contract_name,
                    "constructor",
                    None,
                    tx.return_value.address if tx.status == 1 else None,
                    args,
                    value,
                    CallTraceKind.CREATE,
                    1,
                    tx.chain,
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
                    value,
                    CallTraceKind.CALL,
                    1,
                    tx.chain,
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
                        value,
                        CallTraceKind.CALL,
                        1,
                        tx.chain,
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
                        value,
                        CallTraceKind.CALL,
                        1,
                        tx.chain,
                        True,
                    )
            else:
                fn_abi = contract_abi[tx_params["data"][:4]]
                output_types = [
                    eth_utils.abi.collapse_if_tuple(cast(Dict[str, Any], arg))
                    for arg in fix_library_abi(fn_abi["inputs"])
                ]
                try:
                    decoded_data = list(
                        eth_abi.abi.decode(output_types, tx_params["data"][4:])
                    )  # pyright: reportGeneralTypeIssues=false
                except eth_abi.exceptions.DecodingError:
                    decoded_data = None
                root_trace = CallTrace(
                    obj,
                    contract_name,
                    fn_abi["name"],
                    tx_params["data"][:4],
                    tx.to.address,
                    decoded_data,
                    value,
                    CallTraceKind.CALL,
                    1,
                    tx.chain,
                )

        current_trace = root_trace

        for i, log in enumerate(trace["structLogs"]):
            assert current_trace is not None
            if current_trace.depth != log["depth"]:
                if trace["structLogs"][i - 1]["op"] in {
                    "CALL",
                    "CALLCODE",
                    "DELEGATECALL",
                    "STATICCALL",
                }:
                    # precompiled contract was called in the previous step
                    assert current_trace is not None
                    current_trace = current_trace._parent
                    fqn_overrides.maps[1].update(fqn_overrides.maps[0])
                    fqn_overrides.maps.pop(0)
                    contracts.pop()
                    values.pop()
                else:
                    assert current_trace.depth == log["depth"]

            if log["op"] in {"CALL", "CALLCODE", "DELEGATECALL", "STATICCALL"}:
                if log["op"] in {"CALL", "CALLCODE"}:
                    value = int(log["stack"][-3], 16)
                    args_offset = int(log["stack"][-4], 16)
                    args_size = int(log["stack"][-5], 16)
                elif log["op"] == "DELEGATECALL":
                    value = values[-1]
                    args_offset = int(log["stack"][-3], 16)
                    args_size = int(log["stack"][-4], 16)
                else:
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
                    if addr <= Address(9):
                        precompiled_info = get_precompiled_info(addr, data)
                    elif tx.chain._fork is not None:
                        explorer_info = get_contract_info_from_explorer(
                            addr, tx.chain.chain_id
                        )

                if fqn is None and explorer_info is None and precompiled_info is None:
                    if addr == Address("0x000000000000000000636F6e736F6c652e6c6f67"):
                        if data[:4] in hardhat_console.abis:
                            fn_abi = hardhat_console.abis[data[:4]]
                            output_types = [
                                eth_utils.abi.collapse_if_tuple(
                                    cast(Dict[str, Any], arg)
                                )
                                for arg in fix_library_abi(fn_abi)
                            ]
                            try:
                                arguments = list(
                                    eth_abi.abi.decode(output_types, data[4:])
                                )  # pyright: reportGeneralTypeIssues=false
                            except eth_abi.exceptions.DecodingError:
                                arguments = None
                        else:
                            arguments = [data]

                        call_trace = CallTrace(
                            None,
                            "console",
                            "log",
                            data[:4],
                            addr,
                            arguments,
                            value,
                            log["op"],
                            current_trace.depth + 1,
                            tx.chain,
                        )
                    else:
                        call_trace = CallTrace(
                            None,
                            None,
                            None,
                            None,
                            addr,
                            [data],
                            value,
                            log["op"],
                            current_trace.depth + 1,
                            tx.chain,
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
                        value,
                        log["op"],
                        current_trace.depth + 1,
                        tx.chain,
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
                            output_types = [
                                eth_utils.abi.collapse_if_tuple(
                                    cast(Dict[str, Any], arg)
                                )
                                for arg in fix_library_abi(fn_abi["inputs"])
                            ]
                            try:
                                arguments = list(
                                    eth_abi.abi.decode(output_types, data[4:])
                                )  # pyright: reportGeneralTypeIssues=false
                            except eth_abi.exceptions.DecodingError:
                                arguments = None
                            fn_name = fn_abi["name"]
                            is_special = False
                        elif "fallback" in contract_abi and (
                            value == 0
                            or contract_abi["fallback"]["stateMutability"] == "payable"
                        ):
                            selector = None
                            fn_name = "fallback"
                            arguments = [data]
                            is_special = True
                        else:
                            selector = None
                            fn_name = None
                            arguments = [data]
                            is_special = True
                    else:
                        selector = None
                        if args_size == 0 and "receive" in contract_abi:
                            fn_name = "receive"
                            arguments = []
                            is_special = True
                        elif "fallback" in contract_abi and (
                            value == 0
                            or contract_abi["fallback"]["stateMutability"] == "payable"
                        ):
                            fn_name = "fallback"
                            arguments = [data]
                            is_special = True
                        else:
                            fn_name = None
                            arguments = [data]
                            is_special = True

                    call_trace = CallTrace(
                        obj,
                        contract_name,
                        fn_name,
                        selector,
                        addr,
                        arguments,
                        value,
                        log["op"],
                        current_trace.depth + 1,
                        tx.chain,
                        is_special,
                    )

                current_trace._subtraces.append(call_trace)
                call_trace._parent = current_trace
                current_trace = call_trace
                contracts.append(fqn)
                values.append(value)
                fqn_overrides.maps.insert(0, {})
            elif log["op"] in {"RETURN", "REVERT", "STOP", "SELFDESTRUCT"}:
                if log["op"] == "REVERT":
                    status = False
                else:
                    status = True

                assert current_trace is not None
                while current_trace._kind == CallTraceKind.INTERNAL:
                    current_trace._status = status
                    current_trace = current_trace._parent
                    assert current_trace is not None

                assert current_trace is not None
                if log["op"] != "REVERT" and len(fqn_overrides.maps) > 1:
                    fqn_overrides.maps[1].update(fqn_overrides.maps[0])
                fqn_overrides.maps.pop(0)

                if current_trace.kind in {CallTraceKind.CREATE, CallTraceKind.CREATE2}:
                    try:
                        address = Address(
                            int(trace["structLogs"][i + 1]["stack"][-1], 16)
                        )
                        if address != Address(0):
                            current_trace._address = address
                            fqn_overrides.maps[0][current_trace.address] = contracts[-1]
                    except IndexError:
                        pass

                current_trace._status = status
                current_trace = current_trace._parent

                contracts.pop()
                values.pop()
            elif log["op"] in {"CREATE", "CREATE2"}:
                value = int(log["stack"][-1], 16)
                offset = int(log["stack"][-2], 16)
                length = int(log["stack"][-3], 16)

                creation_code = read_from_memory(offset, length, log["memory"])
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
                    else:
                        fn_abi = contract_abi["constructor"]
                        output_types = [
                            eth_utils.abi.collapse_if_tuple(cast(Dict[str, Any], arg))
                            for arg in fix_library_abi(fn_abi["inputs"])
                        ]
                        try:
                            args = list(
                                eth_abi.abi.decode(
                                    output_types, creation_code[constructor_offset:]
                                )
                            )  # pyright: reportGeneralTypeIssues=false
                        except eth_abi.exceptions.DecodingError:
                            args = None
                except ValueError:
                    fqn = None
                    obj = None
                    contract_name = None
                    args = []

                assert current_trace is not None
                call_trace = CallTrace(
                    obj,
                    contract_name,
                    "constructor",
                    None,
                    None,  # to be set later
                    args,
                    value,
                    log["op"],
                    current_trace.depth + 1,
                    tx.chain,
                    True,
                )

                current_trace._subtraces.append(call_trace)
                call_trace._parent = current_trace
                current_trace = call_trace
                contracts.append(fqn)
                values.append(value)
                fqn_overrides.maps.insert(0, {})

        return root_trace
