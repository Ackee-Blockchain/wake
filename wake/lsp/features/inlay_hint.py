from enum import IntEnum
from itertools import chain
from typing import Any, List, Optional, Tuple, Union

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
from wake.lsp.context import LspContext
from wake.lsp.lsp_data_model import LspModel
from wake.lsp.utils import uri_to_path


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


async def inlay_hint(
    context: LspContext, params: InlayHintParams
) -> Union[None, List[InlayHint]]:
    if not context.config.lsp.inlay_hints.enable:
        return None

    await context.compiler.output_ready.wait()

    path = uri_to_path(params.text_document.uri).resolve()
    if path not in context.compiler.source_units:
        return None

    start = context.compiler.get_byte_offset_from_line_pos(
        path, params.range.start.line, params.range.start.character
    )
    end = context.compiler.get_byte_offset_from_line_pos(
        path, params.range.end.line, params.range.end.character
    )

    inlay_hints: List[Tuple[InlayHint, str]] = []
    for offset, inlay_hint_items in chain(
        context.compiler.get_detector_inlay_hints(path, (start, end)).items(),
        context.compiler.get_printer_inlay_hints(path, (start, end)).items(),
    ):
        for inlay_hint_options in inlay_hint_items:
            line, col = context.compiler.get_line_pos_from_byte_offset(path, offset)

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
