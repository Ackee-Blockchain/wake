from itertools import chain
from pathlib import Path
from typing import Any, List, Optional, Tuple, Union, Dict, Set

from wake.core import get_logger
from wake.lsp.common_structures import (
    Command,
    MessageType,
    PartialResultParams,
    Range,
    TextDocumentIdentifier,
    TextDocumentRegistrationOptions,
    WorkDoneProgressOptions,
    WorkDoneProgressParams,
)
from wake.lsp.context import LspContext
from wake.lsp.lsp_data_model import LspModel
from wake.lsp.utils.position import changes_to_byte_offset
from wake.lsp.utils.uri import uri_to_path
from wake.core.lsp_provider import CodeLensOptions as ProviderCodeLensOptions

logger = get_logger(__name__)


class CodeLensOptions(WorkDoneProgressOptions):
    resolve_provider: Optional[bool] = None
    """
    Code lens has a resolve provider as well.
    """


class CodeLensRegistrationOptions(TextDocumentRegistrationOptions, CodeLensOptions):
    pass


class CodeLensParams(WorkDoneProgressParams, PartialResultParams):
    text_document: TextDocumentIdentifier
    """
    The document to request code lens for.
    """


class CodeLens(LspModel):
    """
    A code lens represents a command that should be shown along with
    source text, like the number of references, a way to run tests, etc.

    A code lens is _unresolved_ when no command is associated to it. For
    performance reasons the creation of a code lens and resolving should be done
    in two stages
    """

    range: Range
    """
    The range in which this code lens is valid. Should only span a single line.
    """
    command: Optional[Command] = None
    """
    The command this code lens represents.
    """
    data: Optional[Any] = None
    """
    A data entry field that is preserved on a code lens item between
    a code lens and a code lens resolve request.
    """


def _get_code_lens_from_detectors(
    context: LspContext,
    path: Path,
) -> Dict[Tuple[int, int], Set[ProviderCodeLensOptions]]:
    forward_changes = context.compiler.get_detector_forward_changes(path)
    if forward_changes is None:
        return {}

    code_lens = {}
    for offsets, items in context.compiler.get_detector_code_lenses(path).items():
        if len(forward_changes[offsets[0]:offsets[1]]) > 0:
            continue

        new_start = changes_to_byte_offset(forward_changes[0:offsets[0]]) + offsets[0]
        new_end = changes_to_byte_offset(forward_changes[0:offsets[1]]) + offsets[1]
        code_lens[(new_start, new_end)] = items

    return code_lens


def _get_code_lens_from_printers(
    context: LspContext,
    path: Path,
) -> Dict[Tuple[int, int], Set[ProviderCodeLensOptions]]:
    forward_changes = context.compiler.get_printer_forward_changes(path)
    if forward_changes is None:
        return {}

    code_lens = {}
    for offsets, items in context.compiler.get_printer_code_lenses(path).items():
        if len(forward_changes[offsets[0]:offsets[1]]) > 0:
            continue

        new_start = changes_to_byte_offset(forward_changes[0:offsets[0]]) + offsets[0]
        new_end = changes_to_byte_offset(forward_changes[0:offsets[1]]) + offsets[1]
        code_lens[(new_start, new_end)] = items

    return code_lens


async def code_lens(
    context: LspContext, params: CodeLensParams
) -> Union[None, List[CodeLens]]:
    logger.debug(f"Code lens for file {params.text_document.uri} requested")
    if not context.config.lsp.code_lens.enable:
        return None

    path = uri_to_path(params.text_document.uri).resolve()

    code_lens: List[Tuple[CodeLens, str]] = []
    for offsets, code_lens_items in chain(
        _get_code_lens_from_detectors(context, path).items(),
        _get_code_lens_from_printers(context, path).items(),
    ):
        for code_lens_options in code_lens_items:
            lens = CodeLens(
                range=context.compiler.get_early_range_from_byte_offsets(path, offsets),
                command=Command(
                    title=code_lens_options.title,
                    command="Tools-for-Solidity.wake_callback"
                    if code_lens_options.callback_id is not None
                    else "",
                ),
            )
            if code_lens_options.callback_id is not None:
                lens.command.arguments = [  # pyright: ignore reportGeneralTypeIssues
                    params.text_document.uri,
                    code_lens_options.callback_kind,
                    code_lens_options.callback_id,
                ]
            code_lens.append((lens, code_lens_options.sort_tag))

    sort_tags = {sort_tag for _, sort_tag in code_lens}
    sort_tags_priority = context.config.lsp.code_lens.sort_tag_priority + sorted(
        sort_tags - set(context.config.lsp.code_lens.sort_tag_priority)
    )

    code_lens.sort(
        key=lambda x: (
            x[0].range.start.line,
            x[0].range.start.character,
            x[0].range.end.line,
            x[0].range.end.character,
            sort_tags_priority.index(x[1]),
        )
    )
    return [lens for lens, _ in code_lens]
