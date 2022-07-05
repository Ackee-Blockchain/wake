from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional, Tuple

if TYPE_CHECKING:
    from woke.lsp.server import LspServer

from woke.compile.solc_frontend import SolcOutputError, SolcOutputErrorSeverityEnum
from woke.lsp.common_structures import (
    Diagnostic,
    DiagnosticSeverity,
    DocumentUri,
    Position,
    Range,
)
from woke.lsp.context import LspContext
from woke.lsp.lsp_data_model import LspModel
from woke.lsp.methods import RequestMethodEnum
from woke.lsp.utils.uri import path_to_uri

logger = logging.getLogger(__name__)


class PublishDiagnosticsParams(LspModel):
    uri: DocumentUri
    """
    The URI for which diagnostic information is reported.
    """
    version: Optional[int] = None
    """
    Optiona the version number of the document the diagnostics are published
    for.
    
    @since 3.15.0
    """
    diagnostics: List[Diagnostic]
    """
    An array of diagnostic information items.
    """


async def diagnostics_loop(
    server: LspServer, context: LspContext, queue: asyncio.Queue
):
    while True:
        errors: Tuple[Path, List[SolcOutputError]] = await queue.get()

        diagnostics = []
        file = errors[0]
        for error in errors[1]:
            assert error.source_location is not None
            if error.source_location.start >= 0 and error.source_location.end >= 0:
                start = error.source_location.start
                end = error.source_location.end
                range_ = context.compiler.get_range_from_byte_offsets(
                    file, (start, end)
                )
            else:
                range_ = Range(
                    start=Position(line=0, character=0),
                    end=Position(line=0, character=0),
                )

            if error.severity == SolcOutputErrorSeverityEnum.ERROR:
                severity = DiagnosticSeverity.ERROR
            elif error.severity == SolcOutputErrorSeverityEnum.WARNING:
                severity = DiagnosticSeverity.WARNING
            elif error.severity == SolcOutputErrorSeverityEnum.INFO:
                severity = DiagnosticSeverity.INFORMATION
            else:
                assert False, "Unexpected solc output error severity"

            diagnostic = Diagnostic(
                range=range_,
                severity=severity,
                message=error.message,
            )
            diagnostics.append(diagnostic)

        params = PublishDiagnosticsParams(
            uri=DocumentUri(path_to_uri(file)),
            diagnostics=diagnostics,
        )
        await server.send_notification(RequestMethodEnum.PUBLISH_DIAGNOSTICS, params)
