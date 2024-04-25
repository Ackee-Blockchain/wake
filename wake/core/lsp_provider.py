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
    Union,
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
    label: Tuple[str, ...]
    tooltip: Tuple[Optional[str], ...]
    padding_left: bool
    padding_right: bool
    callback_id: Tuple[Optional[str], ...]
    callback_kind: str


class CommandAbc(LspModel):
    command: str


class GoToLocationsCommand(CommandAbc):
    uri: DocumentUri  # pyright: ignore reportInvalidTypeForm
    position: Position
    locations: List[Location]
    multiple: Literal["peek", "gotoAndPeek", "goto"]
    no_results_message: str

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, command="goToLocations")

    @classmethod
    def from_nodes(
        cls,
        start: ir.IrAbc,
        locations: Iterable[ir.IrAbc],
        multiple: Literal["peek", "gotoAndPeek", "goto"],
        no_results_message: str = "No results found",
    ) -> GoToLocationsCommand:
        from wake.lsp.utils import path_to_uri

        pos_line, pos_col = start.source_unit.get_line_col_from_byte_offset(
            start.name_location[0]
            if isinstance(start, ir.DeclarationAbc)
            else start.byte_location[0]
        )

        l = []
        for loc in locations:
            start_line, start_col = loc.source_unit.get_line_col_from_byte_offset(
                loc.name_location[0]
                if isinstance(loc, ir.DeclarationAbc)
                else loc.byte_location[0]
            )
            end_line, end_col = loc.source_unit.get_line_col_from_byte_offset(
                loc.name_location[1]
                if isinstance(loc, ir.DeclarationAbc)
                else loc.byte_location[1]
            )
            l.append(
                Location(
                    uri=DocumentUri(path_to_uri(loc.source_unit.file)),
                    range=Range(
                        start=Position(line=start_line - 1, character=start_col - 1),
                        end=Position(line=end_line - 1, character=end_col - 1),
                    ),
                )
            )

        return cls(
            uri=DocumentUri(path_to_uri(start.source_unit.file)),
            position=Position(line=pos_line - 1, character=pos_col - 1),
            locations=l,
            multiple=multiple,
            no_results_message=no_results_message,
        )


class PeekLocationsCommand(CommandAbc):
    uri: DocumentUri  # pyright: ignore reportInvalidTypeForm
    position: Position
    locations: List[Location]
    multiple: Literal["peek", "gotoAndPeek", "goto"]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, command="peekLocations")

    @classmethod
    def from_nodes(
        cls,
        start: ir.IrAbc,
        locations: Iterable[ir.IrAbc],
        multiple: Literal["peek", "gotoAndPeek", "goto"],
    ) -> PeekLocationsCommand:
        from wake.lsp.utils import path_to_uri

        pos_line, pos_col = start.source_unit.get_line_col_from_byte_offset(
            start.name_location[0]
            if isinstance(start, ir.DeclarationAbc)
            else start.byte_location[0]
        )

        l = []
        for loc in locations:
            start_line, start_col = loc.source_unit.get_line_col_from_byte_offset(
                loc.name_location[0]
                if isinstance(loc, ir.DeclarationAbc)
                else loc.byte_location[0]
            )
            end_line, end_col = loc.source_unit.get_line_col_from_byte_offset(
                loc.name_location[1]
                if isinstance(loc, ir.DeclarationAbc)
                else loc.byte_location[1]
            )
            l.append(
                Location(
                    uri=DocumentUri(path_to_uri(loc.source_unit.file)),
                    range=Range(
                        start=Position(line=start_line - 1, character=start_col - 1),
                        end=Position(line=end_line - 1, character=end_col - 1),
                    ),
                )
            )

        return cls(
            uri=DocumentUri(path_to_uri(start.source_unit.file)),
            position=Position(line=pos_line - 1, character=pos_col - 1),
            locations=l,
            multiple=multiple,
        )


class OpenCommand(CommandAbc):
    uri: DocumentUri  # pyright: ignore reportInvalidTypeForm

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, command="open")


class CopyToClipboardCommand(CommandAbc):
    text: str

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, command="copyToClipboard")


class ShowDotCommand(CommandAbc):
    command = "showDot"
    dot: str

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, command="showDot")


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
        self, path: Path, start: int, end: int, text: str,
    ) -> None:
        self._hovers[path][(start, end)].add(HoverOptions(text, True))

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
        label: Union[str, Iterable[str]],
        *,
        tooltip: Union[Optional[str], Iterable[Optional[str]]] = None,
        on_click: Union[
            Optional[Callable[[], None]], Iterable[Optional[Callable[[], None]]]
        ] = None,
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
        )

    def add_inlay_hint_from_offset(
        self,
        path: Path,
        offset: int,
        label: Union[str, Iterable[str]],
        *,
        tooltip: Union[Optional[str], Iterable[Optional[str]]] = None,
        on_click: Union[
            Optional[Callable[[], None]], Iterable[Optional[Callable[[], None]]]
        ] = None,
        padding_left: bool = True,
        padding_right: bool = True,
    ) -> None:
        if isinstance(label, str):
            label = [label]

        if tooltip is None:
            tooltip = [None] * len(label)
        elif isinstance(tooltip, str):
            tooltip = [tooltip]

        if on_click is None:
            on_click = [None] * len(label)
        elif not isinstance(on_click, (list, tuple)):
            on_click = [on_click]

        if len(label) != len(tooltip) or len(label) != len(on_click):
            raise ValueError("label, tooltip and on_click must have the same length")

        callback_ids = []
        for callback in on_click:
            if callback is not None:
                callback_id = f"callback_{self._callback_counter}"
                self._callbacks[callback_id] = callback
                callback_ids.append(callback_id)
                self._callback_counter += 1
            else:
                callback_ids.append(None)

        self._inlay_hints[path][offset].add(
            InlayHintOptions(
                tuple(label),
                tuple(tooltip),
                padding_left,
                padding_right,
                tuple(callback_ids),
                self._callback_kind,
            )
        )

    def clear(self) -> None:
        self._hovers.clear()
        self._code_lenses.clear()
        self._inlay_hints.clear()
        self._commands.clear()

    def clear_commands(self) -> None:
        self._commands.clear()
