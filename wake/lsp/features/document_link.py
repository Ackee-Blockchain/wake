import logging
from itertools import chain
from typing import Any, List, Optional

from wake.compiler.exceptions import CompilationResolveError
from wake.compiler.source_path_resolver import SourcePathResolver
from wake.compiler.source_unit_name_resolver import SourceUnitNameResolver
from wake.core import get_logger
from wake.lsp.common_structures import (
    DocumentUri,
    PartialResultParams,
    Position,
    Range,
    TextDocumentIdentifier,
    WorkDoneProgressOptions,
    WorkDoneProgressParams,
)
from wake.lsp.context import LspContext
from wake.lsp.lsp_data_model import LspModel
from wake.lsp.utils.uri import path_to_uri, uri_to_path

logger = get_logger(__name__)


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

    path = uri_to_path(params.text_document.uri).resolve()

    document_links = []
    source_unit_name_resolver = SourceUnitNameResolver(context.config)
    source_path_resolver = SourcePathResolver(context.config)

    this_source_unit_name = None
    for include_path in chain(
        context.config.compiler.solc.include_paths, [context.config.project_root_path]
    ):
        try:
            rel_path = str(path.relative_to(include_path).as_posix())
            if this_source_unit_name is None or len(this_source_unit_name) > len(
                rel_path
            ):
                this_source_unit_name = rel_path
        except ValueError:
            continue

    if this_source_unit_name is None:
        return None

    try:
        root = context.parser[path].root_node
    except KeyError:
        return None

    for child in root.children:
        if child.type == "import_directive":
            source_node = child.child_by_field_name("source")

            if source_node is not None:
                import_str = source_node.text.decode("utf-16-le")[1:-1]  # remove quotes
                unit_name = source_unit_name_resolver.resolve_import(
                    this_source_unit_name, import_str
                )

                try:
                    include_path = source_path_resolver.resolve(
                        unit_name, this_source_unit_name, context.parser.files
                    )
                    document_links.append(
                        DocumentLink(
                            range=Range(
                                start=Position(
                                    line=source_node.start_point[0],
                                    character=source_node.start_point[1] // 2,
                                ),
                                end=Position(
                                    line=source_node.end_point[0],
                                    character=source_node.end_point[1] // 2,
                                ),
                            ),
                            target=DocumentUri(path_to_uri(include_path)),
                            tooltip=None,
                            data=None,
                        )
                    )
                except CompilationResolveError:
                    continue

    return document_links
