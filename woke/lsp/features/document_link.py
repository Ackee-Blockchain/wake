import logging
from pathlib import Path
from typing import Any, List, Optional

from woke.lsp.common_structures import (
    DocumentUri,
    PartialResultParams,
    Range,
    TextDocumentIdentifier,
    WorkDoneProgressOptions,
    WorkDoneProgressParams,
)
from woke.lsp.context import LspContext
from woke.lsp.lsp_data_model import LspModel
from woke.lsp.utils.position import changes_to_byte_offset
from woke.lsp.utils.uri import path_to_uri, uri_to_path

logger = logging.getLogger(__name__)


class DocumentLinkOptions(WorkDoneProgressOptions):
    resolve_provider: Optional[bool]
    """
    Document links have a resolve provider as well.
    """


class DocumentLinkParams(WorkDoneProgressParams, PartialResultParams):
    text_document: TextDocumentIdentifier
    """
    The document to provide document links for.
    """


class DocumentLink(LspModel):
    range: Range
    """
    The range this link applies to.
    """
    target: Optional[DocumentUri]
    """
    The uri this link points to. If missing a resolve request is sent later.
    """
    tooltip: Optional[str]
    """
    The tooltip text when you hover over this link.
    
    If a tooltip is provided, it will be displayed in a string that includes
    instructions on how to trigger the link, such as `{0} (ctrl + click)`.
    The specific instructions vary depending on OS, user settings, and
    localization.
    
    @since 3.15.0
    """
    data: Optional[Any]
    """
    A data entry field that is preserved on a document link between a
    DocumentLinkRequest and a DocumentLinkResolveRequest.
    """


async def _get_document_links_from_cache(path: Path, context: LspContext):
    source_unit = context.compiler.last_compilation_source_units[path]
    forward_changes = context.compiler.get_last_compilation_forward_changes(path)
    if forward_changes is None:
        raise Exception("No forward changes found for file")

    document_links = []

    for import_directive in source_unit.imports:
        location = import_directive.import_string_pos

        if len(forward_changes[location[0] : location[1]]) > 0:
            # change at range, skip import
            continue

        new_start = (
            changes_to_byte_offset(forward_changes[0 : location[0]]) + location[0]
        )
        new_end = changes_to_byte_offset(forward_changes[0 : location[1]]) + location[1]

        document_links.append(
            DocumentLink(
                range=context.compiler.get_range_from_byte_offsets(
                    path, (new_start, new_end)
                ),
                target=DocumentUri(path_to_uri(import_directive.imported_file)),
                tooltip=None,
                data=None,
            )
        )

    return document_links


async def document_link(
    context: LspContext, params: DocumentLinkParams
) -> Optional[List[DocumentLink]]:
    logger.debug(f"Requested document links for file {params.text_document.uri}")

    path = uri_to_path(params.text_document.uri).resolve()
    if (
        path not in context.compiler.source_units
        or not context.compiler.output_ready.is_set()
    ):
        try:
            return await _get_document_links_from_cache(path, context)
        except Exception:
            pass

    await context.compiler.output_ready.wait()
    if path not in context.compiler.source_units:
        return None

    source_unit = context.compiler.source_units[path]
    document_links = []

    for import_directive in source_unit.imports:
        document_links.append(
            DocumentLink(
                range=context.compiler.get_range_from_byte_offsets(
                    path, import_directive.import_string_pos
                ),
                target=DocumentUri(path_to_uri(import_directive.imported_file)),
                tooltip=None,
                data=None,
            )
        )

    return document_links
