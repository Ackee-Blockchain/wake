from __future__ import annotations

import enum
import importlib
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.tree import Tree

from woke.testing.core import (
    Address,
    ChainInterface,
    get_contract_internal_jumpdests,
    get_contract_internal_jumps_in,
    get_contract_internal_jumps_out,
    get_contracts_by_fqn,
    get_fqn_from_address,
)
from woke.testing.json_rpc.communicator import TxParams
from woke.testing.utils import read_from_memory


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
    _status: bool
    _value: int
    _kind: CallTraceKind
    _subtraces: List[CallTrace]
    _parent: Optional[CallTrace]

    def __init__(
        self,
        contract_name: Optional[str],
        function_name: str,
        value: int,
        kind: CallTraceKind,
    ):
        self._contract_name = contract_name
        self._function_name = function_name
        self._value = value
        self._kind = kind
        self._status = True
        self._subtraces = []
        self._parent = None

    def __str__(self):
        tree = Tree(self.get_label())
        self.into_tree(tree)

        console = Console()
        with console.capture() as capture:
            console.print(tree)
        return capture.get()

    def into_tree(self, tree: Tree):
        for subtrace in self._subtraces:
            t = tree.add(subtrace.get_label())
            subtrace.into_tree(t)

    def get_label(self) -> str:
        if self.contract_name is not None:
            ret = f"{self.contract_name}.{self.function_name}"
        else:
            ret = self.function_name

        ret += f" {'[green]✓[/green]' if self.status else '[red]✗[/red]'}"

        if self.kind != CallTraceKind.CALL:
            ret += (
                f" \[{self.kind}]"  # pyright: reportInvalidStringEscapeSequence=false
            )

        return ret

    @property
    def contract_name(self) -> Optional[str]:
        return self._contract_name

    @property
    def function_name(self) -> str:
        return self._function_name

    @property
    def status(self) -> bool:
        return self._status

    @property
    def value(self) -> int:
        return self._value

    @property
    def kind(self) -> CallTraceKind:
        return self._kind

    @classmethod
    def from_debug_trace(
        cls,
        trace: Dict[str, Any],
        origin_fqn: Optional[str],
        tx_params: TxParams,
        chain: ChainInterface,
    ):
        contracts = [origin_fqn]
        values = [0 if "value" not in tx_params else tx_params["value"]]
        internal_jumps = []

        contracts_by_fqn = get_contracts_by_fqn()
        contract_internal_jumps_in = get_contract_internal_jumps_in()
        contract_internal_jumps_out = get_contract_internal_jumps_out()
        contract_internal_jumpdests = get_contract_internal_jumpdests()

        if "value" not in tx_params:
            value = 0
        else:
            value = tx_params["value"]

        # TODO contract creation
        if origin_fqn is None or origin_fqn not in contracts_by_fqn:
            assert "to" in tx_params
            root_trace = CallTrace(
                f"Unknown({tx_params['to']})", "<???>", value, CallTraceKind.CALL
            )
        else:
            contract_name = origin_fqn.split(":")[-1]
            module_name, attrs = contracts_by_fqn[origin_fqn]
            obj = getattr(importlib.import_module(module_name), attrs[0])
            for attr in attrs[1:]:
                obj = getattr(obj, attr)
            contract_abi = obj._abi

            if (
                "data" not in tx_params
                or len(tx_params["data"]) == 0
                and "receive" in contract_abi
            ):
                root_trace = CallTrace(
                    contract_name, "<receive>", value, CallTraceKind.CALL
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
                        contract_name, "<fallback>", value, CallTraceKind.CALL
                    )
                else:
                    root_trace = CallTrace(
                        contract_name, "<???>", value, CallTraceKind.CALL
                    )
            else:
                fn_abi = contract_abi[tx_params["data"][:4]]
                root_trace = CallTrace(
                    contract_name, fn_abi["name"], value, CallTraceKind.CALL
                )

        current_trace = root_trace

        for log in trace["structLogs"]:
            if log["op"] in {"CALL", "CALLCODE", "DELEGATECALL", "STATICCALL"}:
                if log["op"] in {"CALL", "CALLCODE"}:
                    value = int(log["stack"][-3], 16)
                elif log["op"] == "DELEGATECALL":
                    value = values[-1]
                else:
                    value = 0

                addr = int(log["stack"][-2], 16)
                fqn = get_fqn_from_address(Address(addr), chain)
                if fqn is None:
                    if Address(addr) == Address(
                        "0x000000000000000000636F6e736F6c652e6c6f67"
                    ):
                        call_trace = CallTrace("console", "log", value, log["op"])
                    else:
                        call_trace = CallTrace(
                            f"Unknown({Address(addr)})", "<???>", value, log["op"]
                        )
                else:
                    contract_name = fqn.split(":")[-1]
                    module_name, attrs = contracts_by_fqn[fqn]
                    obj = getattr(importlib.import_module(module_name), attrs[0])
                    for attr in attrs[1:]:
                        obj = getattr(obj, attr)
                    contract_abi = obj._abi

                    if log["op"] in {"CALL", "CALLCODE"}:
                        args_offset = int(log["stack"][-4], 16)
                        args_size = int(log["stack"][-5], 16)
                    else:
                        args_offset = int(log["stack"][-3], 16)
                        args_size = int(log["stack"][-4], 16)

                    if args_size >= 4:
                        selector = bytes(
                            read_from_memory(args_offset, 4, log["memory"])
                        )
                        if selector in contract_abi:
                            fn_name = contract_abi[selector]["name"]
                        elif "fallback" in contract_abi and (
                            value == 0
                            or contract_abi["fallback"]["stateMutability"] == "payable"
                        ):
                            fn_name = "<fallback>"
                        else:
                            fn_name = "<???>"
                    else:
                        if args_size == 0 and "receive" in contract_abi:
                            fn_name = "<receive>"
                        elif "fallback" in contract_abi and (
                            value == 0
                            or contract_abi["fallback"]["stateMutability"] == "payable"
                        ):
                            fn_name = "<fallback>"
                        else:
                            fn_name = "<???>"

                    call_trace = CallTrace(contract_name, fn_name, value, log["op"])

                assert current_trace is not None
                current_trace._subtraces.append(call_trace)
                call_trace._parent = current_trace
                current_trace = call_trace
                contracts.append(fqn)
                values.append(value)
            elif log["op"] in {"JUMP", "JUMPI"}:
                pc = int(log["stack"][-1], 16)
                fqn = contracts[-1]

                if (
                    fqn in contract_internal_jumps_in
                    and log["pc"] in contract_internal_jumps_in[fqn]
                ):
                    if (
                        fqn in contract_internal_jumpdests
                        and pc in contract_internal_jumpdests[fqn]
                    ):
                        contract_name, function_name = contract_internal_jumpdests[fqn][
                            pc
                        ]
                        assert current_trace is not None
                        if (
                            current_trace.contract_name == contract_name
                            and current_trace.function_name == function_name
                        ):
                            internal_jumps.append(False)
                        else:
                            jump_trace = CallTrace(
                                contract_name,
                                function_name,
                                current_trace._value,
                                CallTraceKind.INTERNAL,
                            )
                            current_trace._subtraces.append(jump_trace)
                            jump_trace._parent = current_trace
                            current_trace = jump_trace
                            internal_jumps.append(True)
                    else:
                        internal_jumps.append(False)

                if (
                    fqn in contract_internal_jumps_out
                    and log["pc"] in contract_internal_jumps_out[fqn]
                ):
                    valid = internal_jumps.pop()
                    if valid:
                        assert current_trace is not None
                        current_trace = current_trace._parent
            elif log["op"] in {"RETURN", "REVERT", "STOP"}:
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
                current_trace._status = status
                current_trace = current_trace._parent

                contracts.pop()
                values.pop()
            elif log["op"] in {"SELFDESTRUCT", "CREATE", "CREATE2"}:
                raise NotImplementedError

        return root_trace