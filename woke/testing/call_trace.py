from __future__ import annotations

import enum
import importlib
import reprlib
from collections import ChainMap
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, cast

import eth_abi
import eth_utils
from rich.console import Console
from rich.tree import Tree

from woke.testing.core import (
    Address,
    Chain,
    get_contracts_by_fqn,
    get_fqn_from_address,
    get_fqn_from_deployment_code,
    process_debug_trace_for_fqn_overrides,
)
from woke.testing.internal import read_from_memory
from woke.testing.json_rpc.communicator import TxParams

from . import hardhat_console

if TYPE_CHECKING:
    from .transactions import TransactionAbc


class CallTraceKind(str, enum.Enum):
    CALL = "CALL"
    DELEGATECALL = "DELEGATECALL"
    STATICCALL = "STATICCALL"
    CALLCODE = "CALLCODE"
    CREATE = "CREATE"
    CREATE2 = "CREATE2"
    INTERNAL = "INTERNAL"


class CallTrace:
    _contract_name: Optional[str]
    _function_name: str
    _function_is_special: bool
    _arguments: List
    _status: bool
    _value: int
    _kind: CallTraceKind
    _depth: int
    _subtraces: List[CallTrace]
    _parent: Optional[CallTrace]
    _address: Optional[Address]

    def __init__(
        self,
        contract_name: Optional[str],
        function_name: str,
        address: Optional[Address],
        arguments: List,
        value: int,
        kind: CallTraceKind,
        depth: int,
        function_is_special: bool = False,
    ):
        self._contract_name = contract_name
        self._function_name = function_name
        self._address = address
        self._arguments = arguments
        self._value = value
        self._kind = kind
        self._depth = depth
        self._function_is_special = function_is_special
        self._status = True
        self._subtraces = []
        self._parent = None

    def __str__(self):
        console = Console()
        tree = Tree(self.get_label(console))
        self._into_tree(tree, console)

        with console.capture() as capture:
            console.print(tree)
        return capture.get()

    __repr__ = __str__

    def _into_tree(self, tree: Tree, console: Console):
        for subtrace in self._subtraces:
            t = tree.add(subtrace.get_label(console))
            subtrace._into_tree(t, console)

    def get_label(self, console: Console) -> str:
        ret = ""
        if self.contract_name is not None:
            ret += f"[bright_magenta]{self.contract_name}[/bright_magenta]."

        if self.function_is_special:
            ret += f"<[bright_magenta]{self.function_name}[/bright_magenta]>"
        else:
            ret += f"[bright_magenta]{self.function_name}[/bright_magenta]"

        if self.kind != CallTraceKind.INTERNAL:
            args = []
            for arg in self.arguments:
                with console.capture() as capture:
                    console.print(reprlib.repr(arg))
                args.append(capture.get().strip())
            ret += f"({', '.join(args)})"

        ret += f" {'[green]✓[/green]' if self.status else '[red]✗[/red]'}"

        if self.kind != CallTraceKind.CALL:
            ret += f" [yellow]\[{self.kind}][/yellow]"  # pyright: reportInvalidStringEscapeSequence=false

        return ret

    @property
    def contract_name(self) -> Optional[str]:
        return self._contract_name

    @property
    def function_name(self) -> str:
        return self._function_name

    @property
    def function_is_special(self) -> bool:
        return self._function_is_special

    @property
    def address(self) -> Optional[Address]:
        return self._address

    @property
    def arguments(self) -> Tuple:
        return tuple(self._arguments)

    @property
    def status(self) -> bool:
        return self._status

    @property
    def value(self) -> int:
        return self._value

    @property
    def kind(self) -> CallTraceKind:
        return self._kind

    @property
    def depth(self) -> int:
        return self._depth

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
            origin_fqn, _ = get_fqn_from_deployment_code(tx.data)
        else:
            if tx.to.address in fqn_overrides:
                origin_fqn = fqn_overrides[tx.to.address]
            else:
                origin_fqn = get_fqn_from_address(
                    tx.to.address, tx.block_number - 1, tx.chain
                )

        contracts = [origin_fqn]
        values = [0 if "value" not in tx_params else tx_params["value"]]

        contracts_by_fqn = get_contracts_by_fqn()

        if "value" not in tx_params:
            value = 0
        else:
            value = tx_params["value"]

        if origin_fqn is None or origin_fqn not in contracts_by_fqn:
            assert "to" in tx_params
            root_trace = CallTrace(
                f"Unknown({tx_params['to']})",
                "???",
                Address(tx_params["to"]),
                [b"" if "data" not in tx_params else tx_params["data"]],
                value,
                CallTraceKind.CALL,
                1,
                True,
            )
        else:
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
                    _, constructor_offset = get_fqn_from_deployment_code(
                        tx_params["data"]
                    )
                    fn_abi = contract_abi["constructor"]
                    output_types = [
                        eth_utils.abi.collapse_if_tuple(cast(Dict[str, Any], arg))
                        for arg in fn_abi["inputs"]
                    ]
                    args = list(
                        eth_abi.abi.decode(
                            output_types, tx_params["data"][constructor_offset:]
                        )
                    )  # pyright: reportGeneralTypeIssues=false
                root_trace = CallTrace(
                    contract_name,
                    "constructor",
                    tx.return_value.address if tx.status == 1 else None,
                    args,
                    value,
                    CallTraceKind.CREATE,
                    1,
                    True,
                )
            elif (
                "data" not in tx_params
                or len(tx_params["data"]) == 0
                and "receive" in contract_abi
            ):
                root_trace = CallTrace(
                    contract_name,
                    "receive",
                    tx.to.address,
                    [],
                    value,
                    CallTraceKind.CALL,
                    1,
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
                        contract_name,
                        "fallback",
                        tx.to.address,
                        [b"" if "data" not in tx_params else tx_params["data"]],
                        value,
                        CallTraceKind.CALL,
                        1,
                        True,
                    )
                else:
                    root_trace = CallTrace(
                        contract_name,
                        "???",
                        tx.to.address,
                        [b"" if "data" not in tx_params else tx_params["data"]],
                        value,
                        CallTraceKind.CALL,
                        1,
                        True,
                    )
            else:
                fn_abi = contract_abi[tx_params["data"][:4]]
                output_types = [
                    eth_utils.abi.collapse_if_tuple(cast(Dict[str, Any], arg))
                    for arg in fn_abi["inputs"]
                ]
                decoded_data = list(
                    eth_abi.abi.decode(output_types, tx_params["data"][4:])
                )  # pyright: reportGeneralTypeIssues=false
                root_trace = CallTrace(
                    contract_name,
                    fn_abi["name"],
                    tx.to.address,
                    decoded_data,
                    value,
                    CallTraceKind.CALL,
                    1,
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
                    fqn = get_fqn_from_address(addr, tx.block_number - 1, tx.chain)
                if fqn is None:
                    if addr == Address("0x000000000000000000636F6e736F6c652e6c6f67"):
                        if data[:4] in hardhat_console.abis:
                            fn_abi = hardhat_console.abis[data[:4]]
                            output_types = [
                                eth_utils.abi.collapse_if_tuple(
                                    cast(Dict[str, Any], arg)
                                )
                                for arg in fn_abi
                            ]
                            arguments = list(
                                eth_abi.abi.decode(output_types, data[4:])
                            )  # pyright: reportGeneralTypeIssues=false
                        else:
                            arguments = [data]

                        call_trace = CallTrace(
                            "console",
                            "log",
                            addr,
                            arguments,
                            value,
                            log["op"],
                            current_trace.depth + 1,
                        )
                    else:
                        call_trace = CallTrace(
                            f"Unknown({addr})",
                            "???",
                            addr,
                            [data],
                            value,
                            log["op"],
                            current_trace.depth + 1,
                            True,
                        )
                else:
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
                                for arg in fn_abi["inputs"]
                            ]
                            arguments = list(
                                eth_abi.abi.decode(output_types, data[4:])
                            )  # pyright: reportGeneralTypeIssues=false
                            fn_name = fn_abi["name"]
                            is_special = False
                        elif "fallback" in contract_abi and (
                            value == 0
                            or contract_abi["fallback"]["stateMutability"] == "payable"
                        ):
                            fn_name = "fallback"
                            arguments = [data]
                            is_special = True
                        else:
                            fn_name = "???"
                            arguments = [data]
                            is_special = True
                    else:
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
                            fn_name = "???"
                            arguments = [data]
                            is_special = True

                    call_trace = CallTrace(
                        contract_name,
                        fn_name,
                        addr,
                        arguments,
                        value,
                        log["op"],
                        current_trace.depth + 1,
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

                deployment_code = read_from_memory(offset, length, log["memory"])
                fqn, constructor_offset = get_fqn_from_deployment_code(deployment_code)

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
                        for arg in fn_abi["inputs"]
                    ]
                    args = list(
                        eth_abi.abi.decode(
                            output_types, deployment_code[constructor_offset:]
                        )
                    )  # pyright: reportGeneralTypeIssues=false

                assert current_trace is not None
                call_trace = CallTrace(
                    contract_name,
                    "constructor",
                    None,  # to be set later
                    args,
                    value,
                    log["op"],
                    current_trace.depth + 1,
                    True,
                )

                current_trace._subtraces.append(call_trace)
                call_trace._parent = current_trace
                current_trace = call_trace
                contracts.append(fqn)
                values.append(value)
                fqn_overrides.maps.insert(0, {})

        return root_trace
