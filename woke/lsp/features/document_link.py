import logging
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


async def document_link(
    context: LspContext, params: DocumentLinkParams
) -> Optional[List[DocumentLink]]:
    logger.debug(f"Requested document links for file {params.text_document.uri}")
    await context.compiler.output_ready.wait()

    document_links = []

    path = uri_to_path(params.text_document.uri).resolve()
    if path in context.compiler.source_units:
        source_unit = context.compiler.source_units[path]

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
