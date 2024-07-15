from enum import IntEnum
from itertools import chain
from pathlib import Path
from typing import Any, List, Optional, Tuple, Union, Set

from wake.lsp.common_structures import (
    Command,
    Location,
    MarkupContent,
    Position,
    Range,
    StaticRegistrationOptions,
    TextDocumentIdentifier,
    TextDocumentRegistrationOptions,
    TextEdit,
    WorkDoneProgressOptions,
    WorkDoneProgressParams,
)
from wake.core.lsp_provider import InlayHintOptions as ProviderInlayHintOptions
from wake.lsp.context import LspContext
from wake.lsp.lsp_data_model import LspModel
from wake.lsp.utils import uri_to_path
from wake.lsp.utils.position import changes_to_byte_offset


class InlayHintOptions(WorkDoneProgressOptions):
    resolve_provider: Optional[bool] = None


class InlayHintRegistrationOptions(
    InlayHintOptions, TextDocumentRegistrationOptions, StaticRegistrationOptions
):
    pass


class InlayHintParams(WorkDoneProgressParams):
    text_document: TextDocumentIdentifier
    range: Range


class InlayHintLabelPart(LspModel):
    value: str
    tooltip: Optional[Union[str, MarkupContent]] = None
    location: Optional[Location] = None
    command: Optional[Command] = None


class InlayHintKind(IntEnum):
    TYPE = 1
    PARAMETER = 2


class InlayHint(LspModel):
    position: Position
    label: Union[str, List[InlayHintLabelPart]]
    kind: Optional[InlayHintKind] = None
    text_edits: Optional[List[TextEdit]] = None
    tooltip: Optional[Union[str, MarkupContent]] = None
    padding_left: Optional[bool] = None
    padding_right: Optional[bool] = None
    data: Optional[Any] = None


def _get_inlay_hints_from_detectors(
    context: LspContext,
    path: Path,
    start: int,
    end: int,
) -> List[Tuple[int, Set[ProviderInlayHintOptions]]]:
    backward_changes = context.compiler.get_detector_backward_changes(path)
    forward_changes = context.compiler.get_detector_forward_changes(path)
    if backward_changes is None or forward_changes is None:
        return []

    old_start = changes_to_byte_offset(backward_changes[0:start]) + start
    old_end = changes_to_byte_offset(backward_changes[0:end]) + end

    ret = []
    for offset, inlay_hint_items in context.compiler.get_detector_inlay_hints(path, (old_start, old_end)).items():
        new_offset = changes_to_byte_offset(forward_changes[0:offset]) + offset
        ret.append((new_offset, inlay_hint_items))

    return ret


def _get_inlay_hints_from_printers(
    context: LspContext,
    path: Path,
    start: int,
    end: int,
) -> List[Tuple[int, Set[ProviderInlayHintOptions]]]:
    backward_changes = context.compiler.get_printer_backward_changes(path)
    forward_changes = context.compiler.get_printer_forward_changes(path)
    if backward_changes is None or forward_changes is None:
        return []

    old_start = changes_to_byte_offset(backward_changes[0:start]) + start
    old_end = changes_to_byte_offset(backward_changes[0:end]) + end

    ret = []
    for offset, inlay_hint_items in context.compiler.get_printer_inlay_hints(path, (old_start, old_end)).items():
        if len(forward_changes[offset]) > 0:
            continue

        new_offset = changes_to_byte_offset(forward_changes[0:offset]) + offset
        ret.append((new_offset, inlay_hint_items))

    return ret


async def inlay_hint(
    context: LspContext, params: InlayHintParams
) -> Union[None, List[InlayHint]]:
    if not context.config.lsp.inlay_hints.enable:
        return None

    path = uri_to_path(params.text_document.uri).resolve()

    start = context.compiler.get_early_byte_offset_from_line_pos(
        path, params.range.start.line, params.range.start.character
    )
    end = context.compiler.get_early_byte_offset_from_line_pos(
        path, params.range.end.line, params.range.end.character
    )

    inlay_hints: List[Tuple[InlayHint, str]] = []
    for offset, inlay_hint_items in chain(
        _get_inlay_hints_from_detectors(context, path, start, end),
        _get_inlay_hints_from_printers(context, path, start, end),
    ):
        for inlay_hint_options in inlay_hint_items:
            line, col = context.compiler.get_early_line_pos_from_byte_offset(path, offset)

            parts = []
            for label, tooltip, callback_id in zip(
                inlay_hint_options.label,
                inlay_hint_options.tooltip,
                inlay_hint_options.callback_id,
            ):
                part = InlayHintLabelPart(value=label)
                if tooltip is not None:
                    part.tooltip = tooltip
                if callback_id is not None:
                    part.command = Command(
                        title=label,
                        command="Tools-for-Solidity.wake_callback",
                        arguments=[
                            params.text_document.uri,
                            inlay_hint_options.callback_kind,
                            callback_id,
                        ],
                    )
                parts.append(part)

            inlay_hint = InlayHint(
                position=Position(line=line, character=col),
                label=parts,
                padding_left=inlay_hint_options.padding_left,
                padding_right=inlay_hint_options.padding_right,
            )
            inlay_hints.append((inlay_hint, inlay_hint_options.sort_tag))

    sort_tags = {sort_tag for _, sort_tag in inlay_hints}
    sort_tags_priority = context.config.lsp.inlay_hints.sort_tag_priority + sorted(
        sort_tags - set(context.config.lsp.inlay_hints.sort_tag_priority)
    )

    inlay_hints.sort(
        key=lambda x: (
            x[0].position.line,
            x[0].position.character,
            sort_tags_priority.index(x[1]),
        )
    )

    return [hint for hint, _ in inlay_hints]
