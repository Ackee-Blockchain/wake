import logging
from typing import Any, List, Optional

from woke.lsp.common_structures import (
    DocumentUri,
    PartialResultParams,
    Position,
    Range,
    TextDocumentIdentifier,
    WorkDoneProgressOptions,
    WorkDoneProgressParams,
)
from woke.lsp.context import LspContext
from woke.lsp.lsp_data_model import LspModel
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


def document_link(
    context: LspContext, params: DocumentLinkParams
) -> Optional[List[DocumentLink]]:
    logger.info(f"{context}, {params}")
    logger.info(f"Requested document links for file {params.text_document.uri}")
    context.compiler.output_ready.wait()

    document_links = []

    path = uri_to_path(params.text_document.uri).resolve()
    if path in context.compiler.asts:
        source_unit = context.compiler.source_units[path]

        for import_directive in source_unit.imports:
            byte_offset, byte_length = import_directive.import_string_pos  # type: ignore
            start_line, start_col = context.compiler.get_line_pos_from_byte_offset(
                path, byte_offset
            )
            end_line, end_col = context.compiler.get_line_pos_from_byte_offset(
                path, byte_offset + byte_length
            )
            start = Position(line=start_line, character=start_col)
            end = Position(line=end_line, character=end_col)

            document_links.append(
                DocumentLink(
                    range=Range(start=start, end=end),
                    target=DocumentUri(path_to_uri(import_directive.imported_file)),
                    tooltip=None,
                    data=None,
                )
            )

    return document_links
