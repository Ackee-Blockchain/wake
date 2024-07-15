from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import (
    Callable,
    Collection,
    Dict,
    Iterable,
    List,
    NamedTuple,
    Optional,
    Set,
    Tuple,
    Union,
)

from typing_extensions import Literal

import wake.ir as ir


class HoverOptions(NamedTuple):
    text: str
    on_child: bool


class CodeLensOptions(NamedTuple):
    title: str
    callback_id: Optional[str]
    callback_kind: str
    sort_tag: str


class InlayHintOptions(NamedTuple):
    label: Tuple[str, ...]
    tooltip: Tuple[Optional[str], ...]
    padding_left: bool
    padding_right: bool
    callback_id: Tuple[Optional[str], ...]
    callback_kind: str
    sort_tag: str


@dataclass
class GoToLocationsCommand:
    path: Path
    byte_offset: int
    locations: List[Tuple[Path, int, int]]
    multiple: Literal["peek", "gotoAndPeek", "goto"]
    no_results_message: str

    @classmethod
    def from_offsets(
        cls,
        source_units: Dict[Path, ir.SourceUnit],  # unused
        start_path: Path,
        start_offset: int,
        locations: Iterable[Tuple[Path, int, int]],
        multiple: Literal["peek", "gotoAndPeek", "goto"],
        no_results_message: str = "No results found",
    ) -> GoToLocationsCommand:
        return cls(
            path=start_path,
            byte_offset=start_offset,
            locations=list(locations),
            multiple=multiple,
            no_results_message=no_results_message,
        )

    @classmethod
    def from_nodes(
        cls,
        start: ir.IrAbc,
        locations: Iterable[ir.IrAbc],
        multiple: Literal["peek", "gotoAndPeek", "goto"],
        no_results_message: str = "No results found",
    ) -> GoToLocationsCommand:
        return cls(
            path=start.source_unit.file,
            byte_offset=(
                start.name_location[0]
                if isinstance(start, ir.DeclarationAbc)
                else start.byte_location[0]
            ),
            locations=[
                (loc.source_unit.file, loc.name_location[0], loc.name_location[1])
                if isinstance(loc, ir.DeclarationAbc)
                else (loc.source_unit.file, loc.byte_location[0], loc.byte_location[1])
                for loc in locations
            ],
            multiple=multiple,
            no_results_message=no_results_message,
        )


@dataclass
class PeekLocationsCommand:
    path: Path
    byte_offset: int
    locations: List[Tuple[Path, int, int]]
    multiple: Literal["peek", "gotoAndPeek", "goto"]

    @classmethod
    def from_nodes(
        cls,
        start: ir.IrAbc,
        locations: Iterable[ir.IrAbc],
        multiple: Literal["peek", "gotoAndPeek", "goto"],
    ) -> PeekLocationsCommand:
        return cls(
            path=start.source_unit.file,
            byte_offset=(
                start.name_location[0]
                if isinstance(start, ir.DeclarationAbc)
                else start.byte_location[0]
            ),
            locations=[
                (loc.source_unit.file, loc.name_location[0], loc.name_location[1])
                if isinstance(loc, ir.DeclarationAbc)
                else (loc.source_unit.file, loc.byte_location[0], loc.byte_location[1])
                for loc in locations
            ],
            multiple=multiple,
        )


@dataclass
class OpenCommand:
    uri: str


@dataclass
class CopyToClipboardCommand:
    text: str


@dataclass
class ShowMessageCommand:
    message: str
    kind: Literal["info", "warning", "error"]


@dataclass
class ShowDotCommand:
    title: str
    dot: str


CommandType = Union[
    GoToLocationsCommand,
    PeekLocationsCommand,
    OpenCommand,
    CopyToClipboardCommand,
    ShowMessageCommand,
    ShowDotCommand,
]


class LspProvider:
    _hovers: Dict[Path, Dict[Tuple[int, int], Set[HoverOptions]]]
    _code_lenses: Dict[Path, Dict[Tuple[int, int], Set[CodeLensOptions]]]
    _inlay_hints: Dict[Path, Dict[int, Set[InlayHintOptions]]]
    _commands: List[CommandType]
    _callbacks: Dict[str, Tuple[str, Callable[[], None]]]
    _callback_counter: int
    _callback_kind: str
    _current_sort_tag: str

    def __init__(self, callback_kind: str) -> None:
        self._hovers = {}
        self._code_lenses = {}
        self._inlay_hints = {}
        self._commands = []
        self._callbacks = {}
        self._callback_counter = 0
        self._callback_kind = callback_kind

    def add_commands(self, commands: List[CommandType]) -> None:
        self._commands.extend(commands)

    def get_commands(self) -> Tuple[CommandType, ...]:
        return tuple(self._commands)

    def get_callback(self, callback_id: str) -> Tuple[str, Callable[[], None]]:
        return self._callbacks[callback_id]

    def add_hover(self, node: ir.IrAbc, text: str, *, on_child: bool = False) -> None:
        if node.source_unit.file not in self._hovers:
            self._hovers[node.source_unit.file] = {}
        if node.byte_location not in self._hovers[node.source_unit.file]:
            self._hovers[node.source_unit.file][node.byte_location] = set()

        self._hovers[node.source_unit.file][node.byte_location].add(
            HoverOptions(text, on_child)
        )

    def add_hover_from_offsets(
        self,
        path: Path,
        start: int,
        end: int,
        text: str,
    ) -> None:
        if path not in self._hovers:
            self._hovers[path] = {}
        if (start, end) not in self._hovers[path]:
            self._hovers[path][(start, end)] = set()

        self._hovers[path][(start, end)].add(HoverOptions(text, True))

    def add_code_lens(
        self,
        node: ir.IrAbc,
        title: str,
        *,
        sort_tag: Optional[str] = None,
        on_click: Optional[Callable[[], None]] = None,
    ) -> None:
        self.add_code_lens_from_offsets(
            node.source_unit.file,
            node.byte_location[0],
            node.byte_location[1],
            title,
            sort_tag=sort_tag,
            on_click=on_click,
        )

    def add_code_lens_from_offsets(
        self,
        path: Path,
        start: int,
        end: int,
        title: str,
        *,
        sort_tag: Optional[str] = None,
        on_click: Optional[Callable[[], None]] = None,
    ) -> None:
        if sort_tag is None:
            sort_tag = self._current_sort_tag

        if on_click is not None:
            callback_id = f"callback_{self._callback_counter}"
            self._callbacks[callback_id] = (sort_tag, on_click)
            self._callback_counter += 1
        else:
            callback_id = None

        if path not in self._code_lenses:
            self._code_lenses[path] = {}
        if (start, end) not in self._code_lenses[path]:
            self._code_lenses[path][(start, end)] = set()

        self._code_lenses[path][(start, end)].add(
            CodeLensOptions(title, callback_id, self._callback_kind, sort_tag)
        )

    def add_inlay_hint(
        self,
        node: ir.IrAbc,
        label: Union[str, Collection[str]],
        *,
        tooltip: Union[Optional[str], Collection[Optional[str]]] = None,
        on_click: Union[
            Optional[Callable[[], None]], Collection[Optional[Callable[[], None]]]
        ] = None,
        sort_tag: Optional[str] = None,
        padding_left: bool = True,
        padding_right: bool = True,
    ) -> None:
        self.add_inlay_hint_from_offset(
            node.source_unit.file,
            node.byte_location[1],
            label,
            tooltip=tooltip,
            padding_left=padding_left,
            padding_right=padding_right,
            on_click=on_click,
            sort_tag=sort_tag,
        )

    def add_inlay_hint_from_offset(
        self,
        path: Path,
        offset: int,
        label: Union[str, Collection[str]],
        *,
        tooltip: Union[Optional[str], Collection[Optional[str]]] = None,
        on_click: Union[
            Optional[Callable[[], None]], Collection[Optional[Callable[[], None]]]
        ] = None,
        sort_tag: Optional[str] = None,
        padding_left: bool = True,
        padding_right: bool = True,
    ) -> None:
        if isinstance(label, str):
            label = [label]

        if sort_tag is None:
            sort_tag = self._current_sort_tag

        if tooltip is None:
            tooltip = [None] * len(label)
        elif isinstance(tooltip, str):
            tooltip = [tooltip]

        if on_click is None:
            on_click = [None] * len(label)
        elif not isinstance(on_click, (list, tuple)):
            on_click = [on_click]  # pyright: ignore reportAssignmentType

        assert isinstance(on_click, (list, tuple))

        if len(label) != len(tooltip) or len(label) != len(on_click):
            raise ValueError("label, tooltip and on_click must have the same length")

        callback_ids = []
        for callback in on_click:
            if callback is not None:
                callback_id = f"callback_{self._callback_counter}"
                self._callbacks[callback_id] = (sort_tag, callback)
                callback_ids.append(callback_id)
                self._callback_counter += 1
            else:
                callback_ids.append(None)

        if path not in self._inlay_hints:
            self._inlay_hints[path] = {}
        if offset not in self._inlay_hints[path]:
            self._inlay_hints[path][offset] = set()

        self._inlay_hints[path][offset].add(
            InlayHintOptions(
                tuple(label),
                tuple(tooltip),
                padding_left,
                padding_right,
                tuple(callback_ids),
                self._callback_kind,
                sort_tag,
            )
        )

    def clear(self) -> None:
        self._hovers.clear()
        self._code_lenses.clear()
        self._inlay_hints.clear()
        self._commands.clear()

    def clear_commands(self) -> None:
        self._commands.clear()
