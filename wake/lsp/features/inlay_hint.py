from enum import IntEnum
from itertools import chain
from typing import Any, List, Optional, Union

from wake.lsp.common_structures import (
    Command,
    Location,
    MarkupContent,
    MarkupKind,
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
    resolve_provider: Optional[bool]


class InlayHintRegistrationOptions(
    InlayHintOptions, TextDocumentRegistrationOptions, StaticRegistrationOptions
):
    pass


class InlayHintParams(WorkDoneProgressParams):
    text_document: TextDocumentIdentifier
    range: Range


class InlayHintLabelPart(LspModel):
    value: str
    tooltip: Optional[Union[str, MarkupContent]]
    location: Optional[Location]
    command: Optional[Command]


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

    inlay_hints = []
    for offset, inlay_hint_items in chain(
        context.detectors_lsp_provider.get_inlay_hints(path, (start, end)).items(),
        context.printers_lsp_provider.get_inlay_hints(path, (start, end)).items(),
    ):
        for inlay_hint_options in inlay_hint_items:
            line, col = context.compiler.get_line_pos_from_byte_offset(path, offset)
            inlay_hint = InlayHint(
                position=Position(line=line, character=col),
                label=inlay_hint_options.label,
                padding_left=inlay_hint_options.padding_left,
                padding_right=inlay_hint_options.padding_right,
            )
            if inlay_hint_options.tooltip is not None:
                inlay_hint.tooltip = MarkupContent(
                    kind=MarkupKind.MARKDOWN, value=inlay_hint_options.tooltip
                )
            inlay_hints.append(inlay_hint)

    return inlay_hints
