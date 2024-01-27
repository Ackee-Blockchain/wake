from collections import defaultdict
from pathlib import Path
from typing import DefaultDict, Dict, NamedTuple, Optional, Set, Tuple

import wake.ir as ir


class HoverOptions(NamedTuple):
    text: str
    on_child: bool


class CodeLensOptions(NamedTuple):
    title: str


class InlayHintOptions(NamedTuple):
    label: str
    tooltip: Optional[str]
    padding_left: bool
    padding_right: bool


class LspProvider:
    _hovers: DefaultDict[Path, DefaultDict[Tuple[int, int], Set[HoverOptions]]]
    _code_lenses: DefaultDict[Path, DefaultDict[Tuple[int, int], Set[CodeLensOptions]]]
    _inlay_hints: DefaultDict[Path, DefaultDict[int, Set[InlayHintOptions]]]

    def __init__(self) -> None:
        self._hovers = defaultdict(lambda: defaultdict(set))
        self._code_lenses = defaultdict(lambda: defaultdict(set))
        self._inlay_hints = defaultdict(lambda: defaultdict(set))

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

    def add_code_lens(self, node: ir.IrAbc, title: str) -> None:
        self._code_lenses[node.source_unit.file][node.byte_location].add(
            CodeLensOptions(title)
        )

    def add_code_lens_from_offsets(
        self, path: Path, start: int, end: int, title: str
    ) -> None:
        self._code_lenses[path][(start, end)].add(CodeLensOptions(title))

    def add_inlay_hint(
        self,
        node: ir.IrAbc,
        label: str,
        *,
        tooltip: Optional[str] = None,
        padding_left: bool = True,
        padding_right: bool = True,
    ) -> None:
        self._inlay_hints[node.source_unit.file][node.byte_location[1]].add(
            InlayHintOptions(label, tooltip, padding_left, padding_right)
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
    ) -> None:
        self._inlay_hints[path][offset].add(
            InlayHintOptions(label, tooltip, padding_left, padding_right)
        )

    def clear(self) -> None:
        self._hovers.clear()
        self._code_lenses.clear()
        self._inlay_hints.clear()
