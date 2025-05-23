from __future__ import annotations

import reprlib
from collections import ChainMap
from dataclasses import dataclass
from typing import (
    TYPE_CHECKING,
    AbstractSet,
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Optional,
    Tuple,
    Union,
    cast,
)

import eth_abi
import eth_abi.abi
import eth_abi.exceptions
import eth_utils
from rich.console import Console
from rich.highlighter import RegexHighlighter
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
    get_fqn_from_address,
    get_fqn_from_creation_code,
)
from .globals import get_config, get_verbosity
from .internal import read_from_memory
from .utils import get_name_abi_from_explorer_cached

if TYPE_CHECKING:
    from wake.config import WakeConfig


class ReprHighlighter(RegexHighlighter):
    """Highlights the text typically produced from ``__repr__`` methods."""

    base_style = "repr."
    highlights = [
        r"(?P<tag_start><)(?P<tag_name>[-\w.:|]*)(?P<tag_contents>[\w\W]*)(?P<tag_end>>)",
        r'(?P<attrib_name>[\w_]{1,50})=(?P<attrib_value>"?[\w_]+"?)?',
        r"(?P<brace>[][{}()])",
        "|".join(
            [
                r"(?P<ipv4>[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3})",
                r"(?P<ipv6>([A-Fa-f0-9]{1,4}::?){1,7}[A-Fa-f0-9]{1,4})",
                r"(?P<eui64>(?:[0-9A-Fa-f]{1,2}-){7}[0-9A-Fa-f]{1,2}|(?:[0-9A-Fa-f]{1,2}:){7}[0-9A-Fa-f]{1,2}|(?:[0-9A-Fa-f]{4}\.){3}[0-9A-Fa-f]{4})",
                r"(?P<eui48>(?:[0-9A-Fa-f]{1,2}-){5}[0-9A-Fa-f]{1,2}|(?:[0-9A-Fa-f]{1,2}:){5}[0-9A-Fa-f]{1,2}|(?:[0-9A-Fa-f]{4}\.){2}[0-9A-Fa-f]{4})",
                r"(?P<uuid>[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12})",
                r"(?P<call>[\w.]*?)\(",
                r"\b(?P<bool_true>True)\b|\b(?P<bool_false>False)\b|\b(?P<none>None)\b",
                r"(?P<ellipsis>\.\.\.)",
                r"(?P<number_complex>(?<!\w)(?:\-?[0-9]+\.?[0-9]*(?:e[-+]?\d+?)?)(?:[-+](?:[0-9]+\.?[0-9]*(?:e[-+]?\d+)?))?j)",
                r"(?P<number>(?<!\w)-?[0-9]+\.?[0-9]*(e[-+]?\d+)?\b|0x[0-9a-fA-F]+|(?<=\.)[0-9a-fA-F]{2,})",
                r"(?P<path>\B(/[-\w._+]+)*\/)(?P<filename>[-\w._+]*)?",
                r"(?<![\\\w])(?P<str>b?'''.*?(?<!\\)'''|b?'.*?(?<!\\)'|b?\"\"\".*?(?<!\\)\"\"\"|b?\".*?(?<!\\)\")",
                r"(?P<url>(file|https|http|ws|wss)://[-0-9a-zA-Z$_+!`(),.?/;:&=%#~@]*)",
            ]
        ),
    ]


def get_precompiled_info(
    addr: Address, data: bytes
) -> Tuple[str, Optional[Tuple[Any, ...]], Optional[Tuple[Optional[str], ...]]]:
    if addr == Address(1):
        if len(data) != 128:
            return "ecRecover", None, None
        return (
            "ecRecover",
            (data[:32], data[32:64], data[64:96], data[96:128]),
            ("hash", "v", "r", "s"),
        )
    elif addr == Address(2):
        return "SHA2-256", (data,), ("data",)
    elif addr == Address(3):
        return "RIPEMD-160", (data,), ("data",)
    elif addr == Address(4):
        return "identity", (data,), ("data",)
    elif addr == Address(5):
        if len(data) < 96:
            return "modexp", None, None
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
        )
    elif addr == Address(6):
        if len(data) != 128:
            return "ecAdd", None, None
        x1 = int.from_bytes(data[:32], "big")
        y1 = int.from_bytes(data[32:64], "big")
        x2 = int.from_bytes(data[64:96], "big")
        y2 = int.from_bytes(data[96:128], "big")
        return (
            "ecAdd",
            (x1, y1, x2, y2),
            ("x1", "y1", "x2", "y2"),
        )
    elif addr == Address(7):
        if len(data) != 96:
            return "ecMul", None, None
        x1 = int.from_bytes(data[:32], "big")
        y1 = int.from_bytes(data[32:64], "big")
        s = int.from_bytes(data[64:96], "big")
        return "ecMul", (x1, y1, s), ("x1", "y1", "s")
    elif addr == Address(8):
        if len(data) % (6 * 32) != 0:
            return "ecPairing", None, None
        coords = tuple(
            int.from_bytes(data[i : i + 32], "big") for i in range(0, len(data), 32)
        )
        names = tuple(
            f"y{i // 2 + 1}" if i % 2 else f"x{i // 2 + 1}" for i in range(len(coords))
        )
        return "ecPairing", coords, names
    elif addr == Address(9):
        if len(data) != 4 + 64 + 128 + 16 + 1:
            return "Blake2F", None, None
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
        )
    else:
        raise ValueError(f"Unknown precompiled contract address: {addr}")


def _decode_precompiled(
    addr: Optional[Address], data: bytes
) -> Tuple[List[Any], List[Optional[str]]]:
    if addr == Address(1):
        assert len(data) >= 20
        return [Address(data[-20:].hex())], [None]
    elif Address(2) <= addr <= Address(4):
        return [data], [None]
    elif addr == Address(5):
        return [int.from_bytes(data, "big")], [None]
    elif Address(6) <= addr <= Address(7):
        assert len(data) == 64
        return [int.from_bytes(data[:32], "big"), int.from_bytes(data[32:], "big")], [
            "x",
            "y",
        ]
    elif addr == Address(8):
        return [int.from_bytes(data, "big") > 0], ["success"]
    elif addr == Address(9):
        return [data], [None]
    else:
        raise ValueError(f"Unknown precompiled contract address: {addr}")


def _normalize(arg, a, chain):
    if a["type"] == "address":
        acc = Account(Address(arg), chain)
        if acc.label is not None:
            return acc
        else:
            return Address(arg)
    elif a["type"].endswith("]"):
        if "internalType" in a:
            assert a["internalType"].endswith("]")
            prev_internal_type = a["internalType"]
            a["internalType"] = "[".join(a["internalType"].split("[")[:-1])
        prev_type = a["type"]
        a["type"] = "[".join(a["type"].split("[")[:-1])

        ret = [_normalize(x, a, chain) for x in arg]

        a["type"] = prev_type
        if "internalType" in a:
            a["internalType"] = prev_internal_type

        return ret
    elif (
        a["type"] == "uint8"
        and "internalType" in a
        and a["internalType"].startswith("enum")
    ):
        return CustomIntEnum(a["internalType"][5:], arg)
    elif (
        a["type"] == "tuple"
        and "internalType" in a
        and a["internalType"].startswith("struct")
    ):
        return CustomNamedTuple(
            a["internalType"][7:],
            [c["name"] for c in a["components"]],
            *[
                _normalize(arg[i], a["components"][i], chain)
                for i in range(len(a["components"]))
            ],
        )
    else:
        return arg


def _decode_args(
    abi, data, chain
) -> Tuple[Optional[List], Optional[List[Optional[str]]]]:
    input_types = [
        eth_utils.abi.collapse_if_tuple(cast(Dict[str, Any], arg))
        for arg in fix_library_abi(abi)
    ]
    args = list(
        _normalize(arg, type, chain)
        for arg, type in zip(eth_abi.abi.decode(input_types, data, strict=False), abi)
    )
    arg_names = [arg["name"] for arg in abi]

    return args, arg_names


def _decode_event_args(
    abi, topics, data, chain
) -> Tuple[Optional[List], Optional[List[Optional[str]]]]:
    topic_index = 0
    decoded_indexed = []
    types = []
    non_indexed_abi = []

    for arg in fix_library_abi(abi):
        if arg["indexed"]:
            if arg["type"] in {"string", "bytes", "tuple"} or arg["type"].endswith("]"):
                topic_type = "bytes32"
            else:
                topic_type = arg["type"]

            decoded_indexed.append(
                _normalize(
                    eth_abi.abi.decode([topic_type], topics[topic_index])[0],
                    arg,
                    chain,
                )
            )
            topic_index += 1
        else:
            types.append(eth_utils.abi.collapse_if_tuple(arg))
            non_indexed_abi.append(arg)

    decoded = list(
        _normalize(arg, type, chain)
        for arg, type in zip(eth_abi.abi.decode(types, data), non_indexed_abi)
    )
    merged = []

    for arg in abi:
        if arg["indexed"]:
            merged.append(decoded_indexed.pop(0))
        else:
            merged.append(decoded.pop(0))

    return merged, [arg["name"] for arg in abi]


class CallTraceKind(StrEnum):
    CALL = "CALL"
    DELEGATECALL = "DELEGATECALL"
    STATICCALL = "STATICCALL"
    CALLCODE = "CALLCODE"
    CREATE = "CREATE"
    CREATE2 = "CREATE2"
    INTERNAL = "INTERNAL"  # unused


class CustomNamedTuple(tuple):
    _tuple_name: str
    _field_names: List[str]

    def __new__(cls, tuple_name: str, field_names: Union[str, List[str]], *args):
        if isinstance(field_names, str):
            field_names = field_names.split()

        if len(args) != len(field_names):
            raise TypeError(
                f"{tuple_name} takes {len(field_names)} arguments but {len(args)} were given"
            )

        obj = super().__new__(cls, args)
        obj._tuple_name = tuple_name
        obj._field_names = field_names
        return obj

    def __str__(self):
        fields_str = ", ".join(
            f"{name}={value}" for name, value in zip(self._field_names, self)
        )
        return f"{self._tuple_name}({fields_str})"

    def __repr__(self):
        return self.__str__()


class CustomIntEnum(int):
    _enum_name: str

    def __new__(cls, enum_name: str, value: int):
        obj = super().__new__(cls, value)
        obj._enum_name = enum_name
        return obj

    def __str__(self):
        return f"{self._enum_name}({int(self)})"

    def __repr__(self):
        return self.__str__()


class CustomRepr(reprlib.Repr):
    def repr_CustomNamedTuple(self, obj, level):
        fields_str = ", ".join(
            f"{name}={self.repr(value)}"
            for name, value in zip(
                obj._field_names[: self.maxtuple], obj[: self.maxtuple]
            )
        )
        if len(obj._field_names) > self.maxtuple:
            fields_str += ", ..."
        return f"{obj._tuple_name}({fields_str})"

    def repr_bytes(self, obj, level):
        return "0x" + self.repr(obj.hex())[1:-1]


@dataclass
class CallTraceEvent:
    name: str
    args: List[Any]
    arg_names: List[Optional[str]]


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
    _error_name: Optional[str]
    _error_arguments: Optional[List]
    _error_names: Optional[List[Optional[str]]]
    _revert_data: Optional[bytes]
    _return_value: Optional[List]
    _return_names: Optional[List[Optional[str]]]
    _abi: Dict[bytes, Any]  # used for error and event decoding
    _output_abi: Optional[List[Dict[str, Any]]]  # used for return value decoding
    _events: List[CallTraceEvent]
    _all_events: List[
        CallTraceEvent
    ]  # recursively, in correct order; only saved in root trace

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
        output_abi: Optional[List[Dict[str, Any]]],
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
        self._function_is_special = function_is_special
        self._status = True
        self._subtraces = []
        self._parent = None
        self._error_name = None
        self._error_arguments = None
        self._error_names = None
        self._revert_data = None
        self._return_value = None
        self._return_names = None
        self._output_abi = output_abi
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
        self._events = []
        self._all_events = []

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

        arg_repr = CustomRepr()
        if get_verbosity() > 0:
            arg_repr.maxlevel = 1_000_000
            arg_repr.maxtuple = 1_000_000
            arg_repr.maxlist = 1_000_000
            arg_repr.maxarray = 1_000_000
            arg_repr.maxdict = 1_000_000
            arg_repr.maxset = 1_000_000
            arg_repr.maxfrozenset = 1_000_000
            arg_repr.maxdeque = 1_000_000
            arg_repr.maxstring = 1_000_000
            arg_repr.maxlong = 1_000_000
            arg_repr.maxother = 1_000_000
        else:
            arg_repr.maxstring = 64
            arg_repr.maxother = 44

        if "named_arguments" in options:
            if self.arguments is not None:
                assert self.argument_names is not None
                ret.append("(")
                for i, (arg, arg_name) in enumerate(
                    zip(self.arguments, self.argument_names)
                ):
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
                assert self._return_names is not None

                ret.append("\n➞ ")
                for i, (arg, arg_name) in enumerate(
                    zip(self._return_value, self._return_names)
                ):
                    r = arg_repr.repr(arg)

                    if arg_name is not None and len(arg_name.strip()) > 0:
                        t = Text(f"{arg_name.strip()}={r}")
                    else:
                        t = Text(r)
                    ReprHighlighter().highlight(t)
                    ret.append_text(t)
                    if i < len(self._return_value) - 1:
                        ret.append(", ")

        if "error" in options:
            if self._error_name is not None:
                ret.append("\n➞ ")
                ret.append_text(Text.from_markup(f"[red]{self._error_name}[/red]("))
                for i, (arg, arg_name) in enumerate(
                    zip(self.error_arguments or [], self._error_names or [])
                ):
                    r = arg_repr.repr(arg)

                    if arg_name is not None and len(arg_name.strip()) > 0:
                        t = Text(f"{arg_name.strip()}={r}")
                    else:
                        t = Text(r)
                    ReprHighlighter().highlight(t)
                    ret.append_text(t)
                    if i < len(self.error_arguments or []) - 1:
                        ret.append(", ")
                ret.append(")")

        if "events" in options:
            for event in self._events:
                ret.append("\n  ⚡️ ")
                ret.append_text(
                    Text.from_markup(f"[bright_yellow]{event.name}[/bright_yellow](")
                )
                for i, (arg, arg_name) in enumerate(zip(event.args, event.arg_names)):
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
                    if i < len(event.args) - 1:
                        ret.append(", ")
                ret.append(")")

        return ret

    @property
    def error_string(self) -> Optional[str]:
        if self._error_name is None:
            return None

        ret = f"{self._error_name}("
        for i, (arg, arg_name) in enumerate(
            zip(self.error_arguments or [], self._error_names or [])
        ):
            if arg_name is not None and len(arg_name.strip()) > 0:
                ret += f"{arg_name.strip()}={repr(arg)}"
            else:
                ret += repr(arg)
            if i < len(self.error_arguments or []) - 1:
                ret += ", "
        ret += ")"

        return ret

    @property
    def event_strings(self) -> List[str]:
        # all events recursively, in correct order, excluding events from reverting subtraces
        ret = []
        for event in self._all_events:
            event_string = event.name + "("
            for i, (arg, arg_name) in enumerate(zip(event.args, event.arg_names)):
                if arg_name is not None and len(arg_name.strip()) > 0:
                    event_string += f"{arg_name.strip()}={repr(arg)}"
                else:
                    event_string += repr(arg)

                if i < len(event.args) - 1:
                    event_string += ", "

            event_string += ")"
            ret.append(event_string)

        return ret

    def dict(self, config: WakeConfig) -> Dict[str, Union[Optional[str], List]]:
        options = config.general.call_trace_options
        ret: Dict[str, Union[Optional[str], List]] = {}

        arg_repr = CustomRepr()
        arg_repr.maxlevel = 1_000_000
        arg_repr.maxtuple = 1_000_000
        arg_repr.maxlist = 1_000_000
        arg_repr.maxarray = 1_000_000
        arg_repr.maxdict = 1_000_000
        arg_repr.maxset = 1_000_000
        arg_repr.maxfrozenset = 1_000_000
        arg_repr.maxdeque = 1_000_000
        arg_repr.maxstring = 1_000_000
        arg_repr.maxlong = 1_000_000
        arg_repr.maxother = 1_000_000

        if "contract_name" in options:
            ret["contract_name"] = self.contract_name or "Unknown"
        else:
            ret["contract_name"] = None

        if "address" in options and self.address is not None:
            ret["address"] = Account(self.address, self.chain).label or str(
                self.address
            )
        else:
            ret["address"] = None

        if "function_name" in options:
            if self.function_is_special:
                ret["function_name"] = "<" + (self.function_name or "???") + ">"
            else:
                ret["function_name"] = self.function_name or "???"
        else:
            ret["function_name"] = None

        if "named_arguments" in options:
            if self.arguments is not None:
                assert self.argument_names is not None
                ret["arguments"] = "("
                for i, (arg, arg_name) in enumerate(
                    zip(self.arguments, self.argument_names)
                ):
                    if arg_name is not None and len(arg_name.strip()) > 0:
                        ret["arguments"] += f"{arg_name.strip()}={arg_repr.repr(arg)}"
                    else:
                        ret["arguments"] += arg_repr.repr(arg)

                    if i < len(self.arguments) - 1:
                        ret["arguments"] += ", "
                ret["arguments"] += ")"
            else:
                ret["arguments"] = "(???)"
        elif "arguments" in options:
            if self.arguments is not None:
                ret["arguments"] = "("
                for i, arg in enumerate(self.arguments):
                    ret["arguments"] += arg_repr.repr(arg)
                    if i < len(self.arguments) - 1:
                        ret["arguments"] += ", "
                ret["arguments"] += ")"
            else:
                ret["arguments"] = "(???)"
        else:
            ret["arguments"] = None

        if "status" in options:
            ret["status"] = "✓" if self.status else "✗"
        else:
            ret["status"] = None

        if "call_type" in options:
            ret["call_type"] = self.kind
        else:
            ret["call_type"] = None

        if "value" in options:
            ret["value"] = format_wei(self.value)
        else:
            ret["value"] = None

        if "gas" in options:
            ret["gas"] = f"{self.gas:,}"
        else:
            ret["gas"] = None

        if "sender" in options and self.sender is not None:
            ret["sender"] = str(self.sender)
        else:
            ret["sender"] = None

        if (
            "return_value" in options
            and self._return_value is not None
            and len(self._return_value) > 0
        ):
            assert self._return_names is not None

            ret["return_value"] = ""
            for i, (arg, arg_name) in enumerate(
                zip(self._return_value, self._return_names)
            ):
                if arg_name is not None and len(arg_name.strip()) > 0:
                    ret["return_value"] += f"{arg_name.strip()}={arg_repr.repr(arg)}"
                else:
                    ret["return_value"] += arg_repr.repr(arg)

                if i < len(self._return_value) - 1:
                    ret["return_value"] += ", "
        else:
            ret["return_value"] = None

        if "error" in options and self._error_name is not None:
            ret["error"] = self._error_name + "("

            for i, (arg, arg_name) in enumerate(
                zip(self.error_arguments or [], self._error_names or [])
            ):
                if arg_name is not None and len(arg_name.strip()) > 0:
                    ret["error"] += f"{arg_name.strip()}={arg_repr.repr(arg)}"
                else:
                    ret["error"] += arg_repr.repr(arg)

                if i < len(self.error_arguments or []) - 1:
                    ret["error"] += ", "
            ret["error"] += ")"
        else:
            ret["error"] = None

        if "events" in options:
            ret["events"] = []
            for event in self._events:
                event_string = event.name + "("

                for i, (arg, arg_name) in enumerate(zip(event.args, event.arg_names)):
                    if arg_name is not None and len(arg_name.strip()) > 0:
                        event_string += f"{arg_name.strip()}={repr(arg)}"
                    else:
                        event_string += repr(arg)

                    if i < len(event.args) - 1:
                        event_string += ", "

                event_string += ")"
                ret["events"].append(event_string)
        else:
            ret["events"] = None

        ret["subtraces"] = [sub.dict(config) for sub in self.subtraces]

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

    @property
    def return_names(self) -> Optional[Tuple[Optional[str], ...]]:
        if self._return_names is None:
            return None
        return tuple(self._return_names)

    @classmethod
    def from_debug_trace(
        cls,
        trace: Dict[str, Any],
        tx_params: TxParams,
        chain: Chain,
        to: Optional[Account],
        created_contract: Optional[Account],
        fqn_overrides: ChainMap[Address, Optional[str]],
        fqn_block_number: int,  # the last block before the tx (or call) to fetch fqn
        all_fqns: AbstractSet[str],
        fqn_to_contract_abi: Callable[[str], Tuple[Optional[Contract], Dict]],
    ):
        from .transactions import PanicCodeEnum

        assert tx_params["gas"] != "auto"

        if to is None:
            try:
                origin_fqn, _ = get_fqn_from_creation_code(tx_params["data"])
            except ValueError:
                origin_fqn = None
        else:
            if to.address in fqn_overrides:
                origin_fqn = fqn_overrides[to.address]
            else:
                origin_fqn = get_fqn_from_address(to.address, fqn_block_number, chain)

        contracts = [origin_fqn]
        values = [0 if "value" not in tx_params else tx_params["value"]]
        assert "from" in tx_params
        origin = Account(tx_params["from"], chain)

        if "value" not in tx_params:
            value = 0
        else:
            value = tx_params["value"]

        explorer_info = None
        precompiled_info = None
        if (origin_fqn is None or origin_fqn not in all_fqns) and to is not None:
            if Address(0) < to.address <= Address(9):
                precompiled_info = get_precompiled_info(
                    to.address, b"" if "data" not in tx_params else tx_params["data"]
                )
            elif chain._forked_chain_id is not None:
                explorer_info = get_name_abi_from_explorer_cached(
                    str(to.address),
                    chain._forked_chain_id
                    if chain._forked_chain_id is not None
                    else chain.chain_id,
                )

        if (
            (origin_fqn is None or origin_fqn not in all_fqns)
            and explorer_info is None
            and precompiled_info is None
        ):
            root_trace = CallTrace(
                None,
                None,
                None,
                None,
                None if to is None else to.address,
                [b"" if "data" not in tx_params else tx_params["data"]],
                [None],
                tx_params["gas"],
                value,
                CallTraceKind.CALL,
                1,
                chain,
                origin,
                [],
                {},
                True,
            )
        elif precompiled_info is not None:
            assert to is not None
            precompiled_name, args, arg_names = precompiled_info
            root_trace = CallTrace(
                None,
                "<precompiled>",
                precompiled_name,
                None,
                to.address,
                args,
                arg_names,
                tx_params["gas"],
                value,
                CallTraceKind.CALL,
                1,
                chain,
                origin,
                None,
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
                obj, contract_abi = fqn_to_contract_abi(origin_fqn)

            if to is None:
                if "data" not in tx_params or "constructor" not in contract_abi:
                    args = []
                    arg_names = []
                else:
                    _, constructor_offset = get_fqn_from_creation_code(
                        tx_params["data"]
                    )
                    fn_abi = contract_abi["constructor"]
                    try:
                        args, arg_names = _decode_args(
                            fn_abi["inputs"],
                            tx_params["data"][constructor_offset:],
                            chain,
                        )
                    except Exception:
                        args = None
                        arg_names = None
                root_trace = CallTrace(
                    obj,
                    contract_name,
                    "constructor",
                    None,
                    created_contract.address if created_contract is not None else None,
                    args,
                    arg_names,
                    tx_params["gas"],
                    value,
                    CallTraceKind.CREATE,
                    1,
                    chain,
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
                    to.address,
                    [],
                    [],
                    tx_params["gas"],
                    value,
                    CallTraceKind.CALL,
                    1,
                    chain,
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
                        to.address,
                        [b"" if "data" not in tx_params else tx_params["data"]],
                        [None],
                        tx_params["gas"],
                        value,
                        CallTraceKind.CALL,
                        1,
                        chain,
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
                        to.address,
                        [b"" if "data" not in tx_params else tx_params["data"]],
                        [None],
                        tx_params["gas"],
                        value,
                        CallTraceKind.CALL,
                        1,
                        chain,
                        origin,
                        [],
                        contract_abi,
                        True,
                    )
            else:
                fn_abi = contract_abi[tx_params["data"][:4]]
                try:
                    args, arg_names = _decode_args(
                        fn_abi["inputs"], tx_params["data"][4:], chain
                    )
                except Exception:
                    args = None
                    arg_names = None
                root_trace = CallTrace(
                    obj,
                    contract_name,
                    fn_abi["name"],
                    tx_params["data"][:4],
                    to.address,
                    args,
                    arg_names,
                    tx_params["gas"],
                    value,
                    CallTraceKind.CALL,
                    1,
                    chain,
                    origin,
                    fn_abi["outputs"] if "outputs" in fn_abi else [],
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

                    try:
                        if current_trace._output_abi is not None:
                            return_value, return_names = _decode_args(
                                current_trace._output_abi, data, chain
                            )
                        else:
                            return_value, return_names = _decode_precompiled(
                                current_trace.address, data
                            )
                    except Exception:
                        return_value = [data]
                        return_names = [None]

                    current_trace._return_value = return_value
                    current_trace._return_names = (
                        return_names  # pyright: ignore reportAttributeAccessIssue
                    )
                    current_trace._status = status
                    if current_trace._parent is not None:
                        current_trace._parent._all_events.extend(
                            current_trace._all_events
                        )

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
                        current_trace._error_names = [None]
                        current_trace._revert_data = b""

                        if len(fqn_overrides.maps) > 1:
                            fqn_overrides.maps[1].update(fqn_overrides.maps[0])
                        fqn_overrides.maps.pop(0)

                        current_trace._status = False
                        current_trace._all_events.clear()
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
                    fqn = get_fqn_from_address(addr, fqn_block_number, chain)

                explorer_info = None
                precompiled_info = None
                if fqn is None and addr != Address(
                    "0x000000000000000000636F6e736F6c652e6c6f67"
                ):
                    if Address(0) < addr <= Address(9):
                        precompiled_info = get_precompiled_info(addr, data)
                    elif chain._forked_chain_id is not None:
                        explorer_info = get_name_abi_from_explorer_cached(
                            str(addr),
                            chain._forked_chain_id
                            if chain._forked_chain_id is not None
                            else chain.chain_id,
                        )

                if fqn is None and explorer_info is None and precompiled_info is None:
                    if addr == Address("0x000000000000000000636F6e736F6c652e6c6f67"):
                        if data[:4] in hardhat_console.abis:
                            fn_abi = hardhat_console.abis[data[:4]]
                            try:
                                args, arg_names = _decode_args(fn_abi, data[4:], chain)
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
                            chain,
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
                            chain,
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
                        chain,
                        origin,
                        None,
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
                        obj, contract_abi = fqn_to_contract_abi(fqn)

                    if args_size >= 4:
                        selector = data[:4]
                        if selector in contract_abi:
                            fn_abi = contract_abi[selector]
                            try:
                                args, arg_names = _decode_args(
                                    fn_abi["inputs"], data[4:], chain
                                )
                            except Exception:
                                args = None
                                arg_names = None
                            output_abi = (
                                fn_abi["outputs"] if "outputs" in fn_abi else []
                            )
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
                            output_abi = []
                            is_special = True
                        else:
                            selector = None
                            fn_name = None
                            args = [data]
                            arg_names = [None]
                            output_abi = []
                            is_special = True
                    else:
                        selector = None
                        output_abi = []
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
                        chain,
                        origin,
                        None if precompiled_info is not None else output_abi,
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
                    current_trace._error_names = [None]
                    current_trace._all_events.clear()
                elif log["op"] == "RETURN":
                    data_offset = int(log["stack"][-1], 16)
                    data_size = int(log["stack"][-2], 16)
                    data = bytes(
                        read_from_memory(data_offset, data_size, log["memory"])
                    )

                    try:
                        if current_trace._output_abi is not None:
                            return_value, return_names = _decode_args(
                                current_trace._output_abi, data, chain
                            )
                        else:
                            return_value, return_names = _decode_precompiled(
                                current_trace.address, data
                            )
                    except Exception:
                        return_value = [data]
                        return_names = [None]

                    current_trace._return_value = return_value
                    current_trace._return_names = (
                        return_names  # pyright: ignore reportAttributeAccessIssue
                    )
                    if current_trace._parent is not None:
                        current_trace._parent._all_events.extend(
                            current_trace._all_events
                        )
                elif log["op"] == "REVERT":
                    data_offset = int(log["stack"][-1], 16)
                    data_size = int(log["stack"][-2], 16)
                    data = bytes(
                        read_from_memory(data_offset, data_size, log["memory"])
                    )
                    current_trace._revert_data = data
                    current_trace._all_events.clear()

                    if any(t._revert_data == data for t in current_trace._subtraces):
                        # error propagated from a subtrace
                        subtrace = next(
                            t
                            for t in current_trace._subtraces
                            if t._revert_data == data
                        )
                        current_trace._error_name = subtrace._error_name
                        current_trace._error_arguments = subtrace._error_arguments
                        current_trace._error_names = subtrace._error_names
                    elif len(data) < 4 or data[:4] not in current_trace._abi:
                        current_trace._error_name = "UnknownTransactionRevertedError"
                        current_trace._error_arguments = [data]
                        current_trace._error_names = [None]
                    else:
                        try:
                            error_args, error_names = _decode_args(
                                current_trace._abi[data[:4]]["inputs"],
                                data[4:],
                                chain,
                            )
                            current_trace._error_name = current_trace._abi[data[:4]][
                                "name"
                            ]
                            if (
                                data[:4] == bytes.fromhex("4e487b71")
                                and error_args is not None
                            ):
                                # convert Panic int to enum
                                error_args[0] = PanicCodeEnum(error_args[0])
                            current_trace._error_arguments = error_args
                            current_trace._error_names = error_names
                        except Exception:
                            current_trace._error_name = (
                                "UnknownTransactionRevertedError"
                            )
                            current_trace._error_arguments = [data]
                            current_trace._error_names = [None]
                else:  # STOP, SELFDESTRUCT
                    if current_trace._output_abi is not None:
                        try:
                            # just use a large enough zeroed buffer instead of evaluating the exact size
                            return_value, return_names = _decode_args(
                                current_trace._output_abi, b"\x00" * 100_000, chain
                            )
                        except Exception:
                            return_value = None
                            return_names = None
                    else:
                        # should not really happen
                        return_value, return_names = [], []
                    current_trace._return_value = return_value
                    current_trace._return_names = return_names
                    if current_trace._parent is not None:
                        current_trace._parent._all_events.extend(
                            current_trace._all_events
                        )

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
                    obj, contract_abi = fqn_to_contract_abi(fqn)

                    if "constructor" not in contract_abi:
                        args = []
                        arg_names = []
                    else:
                        fn_abi = contract_abi["constructor"]
                        try:
                            args, arg_names = _decode_args(
                                fn_abi["inputs"],
                                creation_code[constructor_offset:],
                                chain,
                            )
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
                    chain,
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
            elif log["op"] == "LOG0":
                assert current_trace is not None
                data_offset = int(log["stack"][-1], 16)
                data_size = int(log["stack"][-2], 16)
                data = bytes(read_from_memory(data_offset, data_size, log["memory"]))
                event = CallTraceEvent(
                    name="UnknownEvent",
                    args=[data],
                    arg_names=["data"],
                )
                current_trace._events.append(event)
                current_trace._all_events.append(event)
            elif log["op"] in {"LOG1", "LOG2", "LOG3", "LOG4"}:
                assert current_trace is not None
                data_offset = int(log["stack"][-1], 16)
                data_size = int(log["stack"][-2], 16)
                topics_count = int(log["op"][3:])
                topics = [
                    bytes.fromhex(log["stack"][-3 - i][2:].zfill(64))
                    for i in range(topics_count)
                ]
                data = bytes(read_from_memory(data_offset, data_size, log["memory"]))
                try:
                    event_args, event_names = _decode_event_args(
                        current_trace._abi[topics[0]]["inputs"],
                        topics[1:],
                        data,
                        chain,
                    )
                    event = CallTraceEvent(
                        name=current_trace._abi[topics[0]]["name"],
                        args=event_args,
                        arg_names=event_names,
                    )
                    current_trace._events.append(event)
                    current_trace._all_events.append(event)
                except Exception as ex:
                    event = CallTraceEvent(
                        name="UnknownEvent",
                        args=topics + [data],
                        arg_names=[f"topic{i}" for i in range(topics_count)] + ["data"],
                    )
                    current_trace._events.append(event)
                    current_trace._all_events.append(event)

        return root_trace
