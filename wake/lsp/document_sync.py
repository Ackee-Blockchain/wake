from enum import IntEnum
from typing import List, Optional, Union

from .common_structures import (
    Range,
    TextDocumentIdentifier,
    TextDocumentItem,
    TextDocumentRegistrationOptions,
    VersionedTextDocumentIdentifier,
)
from .lsp_data_model import LspModel


class TextDocumentSyncKind(IntEnum):
    NONE = 0
    """
    Documents should not be synced at all.
    """
    FULL = 1
    """
    Documents are synced by always sending the full content
    of the document.
    """
    INCREMENTAL = 2
    """
    Documents are synced by sending the full content on open.
    After that only incremental updates to the document are
    send.Documents are synced by sending the full content on open.
    After that only incremental updates to the document are send.
    """


class SaveOptions(LspModel):
    include_text: Optional[bool]


class TextDocumentSyncOptions(LspModel):
    open_close: Optional[bool] = None
    """
    Open and close notifications are sent to the server. If omitted open
    close notification should not be sent.
    """
    change: Optional[TextDocumentSyncKind] = None
    will_save: Optional[bool] = None
    will_save_wait_until: Optional[bool] = None
    save: Optional[Union[bool, SaveOptions]] = None


class DidOpenTextDocumentParams(LspModel):
    text_document: TextDocumentItem


class TextDocumentChangeRegistrationOptions(TextDocumentRegistrationOptions):
    sync_kind: TextDocumentSyncKind


class TextDocumentContentChangeEvent(LspModel):
    range: Range
    """
    The range of the document that changed.
    """
    range_length: Optional[int]  # uint ?
    """
    The optional length of the range that got replaced.
    """
    text: str
    """
    The new text for the provided range.
    """


class DidChangeTextDocumentParams(LspModel):
    text_document: VersionedTextDocumentIdentifier
    content_changes: List[TextDocumentContentChangeEvent]


class TextDocumentSaveReason(IntEnum):
    MANUAL = 1
    AFTER_DELAY = 2
    FOCUS_OUT = 3


class WillSaveTextDocumentParams(LspModel):
    text_document: TextDocumentIdentifier
    reason: TextDocumentSaveReason


class DidSaveTextDocumentParams(LspModel):
    text_document: TextDocumentIdentifier
    text: Optional[str]


class TextDocumentSaveRegistrationOptions(TextDocumentRegistrationOptions):
    text_document: TextDocumentIdentifier
    """
    The document that was saved.
    """
    text: Optional[str]


class DidCloseTextDocumentParams(LspModel):
    text_document: TextDocumentIdentifier
    """
    The document that was closed.
    """
