import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, DefaultDict, Dict, List, Optional, Type, Union

from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax, SyntaxTheme
from rich.tree import Tree

import woke.cli.console
from woke.ast.ir.abc import IrAbc
from woke.ast.ir.meta.source_unit import SourceUnit

logger = logging.getLogger(__name__)


@dataclass
class DetectorResult:
    ir_node: IrAbc
    message: str
    related_info: List["DetectorResult"] = field(default_factory=list)


@dataclass
class DetectionResult:
    result: DetectorResult
    code: int
    string_id: str


@dataclass
class Detector:
    code: int
    string_id: str
    func: Callable[[IrAbc], Optional[DetectorResult]]


detectors: Dict[Type[IrAbc], List[Detector]] = defaultdict(list)


def detect(source_units: Dict[Path, SourceUnit]) -> List[DetectionResult]:
    results: DefaultDict[str, DefaultDict[str, List[DetectionResult]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for path, source_unit in source_units.items():
        for ir_node in source_unit:
            for d in detectors[type(ir_node)]:
                result = d.func(ir_node)
                if result is not None:
                    results[d.string_id][source_unit.source_unit_name].append(
                        DetectionResult(result, d.code, d.string_id)
                    )
    ret = []
    sorted_detectors = sorted(results.keys())
    for detector_id in sorted_detectors:
        sorted_files = sorted(results[detector_id].keys())
        for file in sorted_files:
            ret.extend(
                sorted(
                    results[detector_id][file],
                    key=lambda d: d.result.ir_node.byte_location[0],
                )
            )
    return ret


def print_detectors(theme: str = "monokai") -> None:
    applied_detectors = set()
    for d in detectors.values():
        for detector in d:
            applied_detectors.add((detector.string_id, detector.func.__doc__))

    detectors_list = "Using the following detectors:\n- " + "\n- ".join(
        f"{d[0]}\n\t{d[1]}" for d in sorted(applied_detectors)
    )
    woke.cli.console.console.print(
        Markdown(detectors_list, inline_code_theme=theme, inline_code_lexer="solidity")
    )


def print_detection(
    result: DetectionResult, theme: Union[str, SyntaxTheme] = "monokai"
) -> None:
    def print_result(detector_result: DetectorResult, tree: Optional[Tree]) -> Tree:
        source_unit = detector_result.ir_node
        while source_unit is not None:
            if isinstance(source_unit, SourceUnit):
                break
            source_unit = source_unit.parent
        assert isinstance(source_unit, SourceUnit)

        tmp_lines = re.split(b"(\r?\n)", source_unit.file_source)
        lines: List[bytes] = []
        for line in tmp_lines:
            if line in {b"\r\n", b"\n"}:
                lines[-1] += line
            else:
                lines.append(line)

        offset = 0
        line_index = 0
        while offset <= detector_result.ir_node.byte_location[0]:
            offset += len(lines[line_index])
            line_index += 1
        line_index -= 1

        source = ""
        start_line_index = max(0, line_index - 3)
        end_line_index = min(len(lines), line_index + 3)
        for i in range(start_line_index, end_line_index):
            source += lines[i].decode("utf-8")

        panel = Panel.fit(
            Syntax(
                source,
                "solidity",
                theme=theme,
                line_numbers=True,
                start_line=(start_line_index + 1),
                highlight_lines={line_index + 1},
            ),
            title=detector_result.message,
            title_align="left",
            subtitle=source_unit.source_unit_name,
            subtitle_align="left",
        )

        if tree is None:
            t = Tree(panel)
        else:
            t = tree.add(panel)

        for additional_result in detector_result.related_info:
            print_result(additional_result, t)

        return t

    woke.cli.console.console.print("\n")
    tree = print_result(result.result, None)
    woke.cli.console.console.print(tree)


def detector(ir_type: Type[IrAbc], code: int, string_id: str):
    def decorator(func):
        detectors[ir_type].append(Detector(code, string_id, func))
        return func

    return decorator
