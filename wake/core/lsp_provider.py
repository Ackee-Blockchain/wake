from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import (
    Callable,
    DefaultDict,
    Dict,
    Iterable,
    List,
    NamedTuple,
    Optional,
    Set,
    Tuple,
)

from typing_extensions import Literal

import wake.ir as ir
from wake.lsp.common_structures import DocumentUri, Location, LspModel, Position, Range


class HoverOptions(NamedTuple):
    text: str
    on_child: bool


class CodeLensOptions(NamedTuple):
    title: str
    callback_id: Optional[str]
    callback_kind: str


class InlayHintOptions(NamedTuple):
    label: str
    tooltip: Optional[str]
    padding_left: bool
    padding_right: bool
    callback_id: Optional[str]
    callback_kind: str


class CommandAbc(LspModel):
    command: str


class GoToLocationsCommand(CommandAbc):
    command = "goToLocations"
    uri: DocumentUri
    position: Position
    locations: List[Position]
    multiple: Literal["peek", "gotoAndPeek", "goto"]
    no_results_message: str


class PeekLocationsCommand(CommandAbc):
    command = "peekLocations"
    uri: DocumentUri
    position: Position
    locations: List[Location]
    multiple: Literal["peek", "gotoAndPeek", "goto"]

    @classmethod
    def from_nodes(
        cls,
        start: ir.IrAbc,
        locations: Iterable[ir.IrAbc],
        multiple: Literal["peek", "gotoAndPeek", "goto"],
    ) -> PeekLocationsCommand:
        from wake.lsp.utils import path_to_uri

        start_line, start_col = start.source_unit.get_line_col_from_byte_offset(
            start.byte_location[0]
        )

        l = []
        for loc in locations:
            start_line, start_col = loc.source_unit.get_line_col_from_byte_offset(
                loc.byte_location[0]
            )
            end_line, end_col = loc.source_unit.get_line_col_from_byte_offset(
                loc.byte_location[1]
            )
            l.append(
                Location(
                    uri=DocumentUri(path_to_uri(loc.source_unit.file)),
                    range=Range(
                        start=Position(line=start_line, character=start_col),
                        end=Position(line=end_line, character=end_col),
                    ),
                )
            )

        return cls(  # pyright: ignore reportGeneralTypeIssues
            uri=DocumentUri(path_to_uri(start.source_unit.file)),
            position=Position(line=start_line, character=start_col),
            locations=l,
            multiple=multiple,
        )


class OpenCommand(CommandAbc):
    command = "open"
    uri: DocumentUri


class CopyToClipboardCommand(CommandAbc):
    command = "copyToClipboard"
    text: str


class ShowDotCommand(CommandAbc):
    command = "showDot"
    dot: str


class LspProvider:
    _hovers: DefaultDict[Path, DefaultDict[Tuple[int, int], Set[HoverOptions]]]
    _code_lenses: DefaultDict[Path, DefaultDict[Tuple[int, int], Set[CodeLensOptions]]]
    _inlay_hints: DefaultDict[Path, DefaultDict[int, Set[InlayHintOptions]]]
    _commands: List[CommandAbc]
    _callbacks: Dict[str, Callable[[], None]]
    _callback_counter: int
    _callback_kind: str

    def __init__(self, callback_kind: str) -> None:
        self._hovers = defaultdict(lambda: defaultdict(set))
        self._code_lenses = defaultdict(lambda: defaultdict(set))
        self._inlay_hints = defaultdict(lambda: defaultdict(set))
        self._commands = []
        self._callbacks = {}
        self._callback_counter = 0
        self._callback_kind = callback_kind

    def add_commands(self, commands: List[CommandAbc]) -> None:
        self._commands.extend(commands)

    def get_commands(self) -> Tuple[CommandAbc, ...]:
        return tuple(self._commands)

    def get_callback(self, callback_id: str) -> Callable[[], None]:
        return self._callbacks[callback_id]

    def get_hovers(
        self, path: Path, byte_offset: int, nested_most_node_offsets: Tuple[int, int]
    ) -> Set[HoverOptions]:
        ret = set()
        for (start, end), hovers in self._hovers[path].items():
            for hover in hovers:
                if not (start <= byte_offset <= end):
                    continue
                if (
                    hover.on_child
                    or nested_most_node_offsets[0] == start
                    and nested_most_node_offsets[1] == end
                ):
                    ret.add(hover)
        return ret

    def get_code_lenses(
        self, path: Path
    ) -> Dict[Tuple[int, int], Set[CodeLensOptions]]:
        return self._code_lenses[path]

    def get_inlay_hints(
        self, path: Path, offsets: Tuple[int, int]
    ) -> Dict[int, Set[InlayHintOptions]]:
        ret = defaultdict(set)
        for offset, hints in self._inlay_hints[path].items():
            if offsets[0] <= offset <= offsets[1]:
                ret[offset].update(hints)
        return ret

    def add_hover(self, node: ir.IrAbc, text: str, *, on_child: bool = False) -> None:
        self._hovers[node.source_unit.file][node.byte_location].add(
            HoverOptions(text, on_child)
        )

    def add_hover_from_offsets(
        self, path: Path, start: int, end: int, text: str, *, on_child: bool = False
    ) -> None:
        self._hovers[path][(start, end)].add(HoverOptions(text, on_child))

    def add_code_lens(
        self,
        node: ir.IrAbc,
        title: str,
        *,
        on_click: Optional[Callable[[], None]] = None,
    ) -> None:
        self.add_code_lens_from_offsets(
            node.source_unit.file,
            node.byte_location[0],
            node.byte_location[1],
            title,
            on_click=on_click,
        )

    def add_code_lens_from_offsets(
        self,
        path: Path,
        start: int,
        end: int,
        title: str,
        *,
        on_click: Optional[Callable[[], None]] = None,
    ) -> None:
        if on_click is not None:
            callback_id = f"callback_{self._callback_counter}"
            self._callbacks[callback_id] = on_click
            self._callback_counter += 1
        else:
            callback_id = None

        self._code_lenses[path][(start, end)].add(
            CodeLensOptions(title, callback_id, self._callback_kind)
        )

    def add_inlay_hint(
        self,
        node: ir.IrAbc,
        label: str,
        *,
        tooltip: Optional[str] = None,
        padding_left: bool = True,
        padding_right: bool = True,
        on_click: Optional[Callable[[], None]] = None,
    ) -> None:
        self.add_inlay_hint_from_offset(
            node.source_unit.file,
            node.byte_location[1],
            label,
            tooltip=tooltip,
            padding_left=padding_left,
            padding_right=padding_right,
            on_click=on_click,
        )

    def add_inlay_hint_from_offset(
        self,
        path: Path,
        offset: int,
        label: str,
        *,
        tooltip: Optional[str] = None,
        padding_left: bool = True,
        padding_right: bool = True,
        on_click: Optional[Callable[[], None]] = None,
    ) -> None:
        if on_click is not None:
            callback_id = f"callback_{self._callback_counter}"
            self._callbacks[callback_id] = on_click
            self._callback_counter += 1
        else:
            callback_id = None

        self._inlay_hints[path][offset].add(
            InlayHintOptions(
                label,
                tooltip,
                padding_left,
                padding_right,
                callback_id,
                self._callback_kind,
            )
        )

    def clear(self) -> None:
        self._hovers.clear()
        self._code_lenses.clear()
        self._inlay_hints.clear()
        self._commands.clear()
