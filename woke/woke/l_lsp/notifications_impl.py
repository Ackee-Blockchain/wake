import logging
from typing import Dict, Callable, Tuple, Type

from .common_structures import *
from .context import LspContext
from .document_sync import (
    DidOpenTextDocumentParams,
    DidChangeTextDocumentParams,
    WillSaveTextDocumentParams,
    DidSaveTextDocumentParams,
    DidCloseTextDocumentParams,
)
from .methods import RequestMethodEnum

logger = logging.getLogger(__name__)

"""
Notification methods just handle what they have to
No return/response necessary
"""

######################
#  client -> server  #
######################


def _initialized(context: LspContext, params: InitializedParams) -> None:
    # probably not really useful
    pass


def _text_document_did_open(
    context: LspContext, params: DidOpenTextDocumentParams
) -> None:
    context.compiler.add_change(params)


def _text_document_did_change(
    context: LspContext, params: DidChangeTextDocumentParams
) -> None:
    context.compiler.add_change(params)


def _text_document_will_save(
    context: LspContext, params: WillSaveTextDocumentParams
) -> None:
    pass


def _text_document_did_save(
    context: LspContext, params: DidSaveTextDocumentParams
) -> None:
    pass


def _text_document_did_close(
    context: LspContext, params: DidCloseTextDocumentParams
) -> None:
    context.compiler.add_change(params)


def handle_client_to_server_notification(
    context: LspContext, notification: str, params: Optional[Dict]
) -> None:
    try:
        n, params_type = _notification_mapping[notification]
    except KeyError:
        logger.error(f"Incoming notification type '{notification}' not implemented.")
        raise NotImplementedError()

    if params_type is not None:
        n(context, params_type.parse_obj(params))
    else:
        n(context, None)


"""
Mapping for all the notifications defined by LSP Specification
https://microsoft.github.io/language-server-protocol/specifications/specification-current/
"""
_notification_mapping: Dict[
    str, Tuple[Callable[[LspContext, Any], None], Optional[Type[LspModel]]]
] = {
    RequestMethodEnum.INITIALIZED: (_initialized, InitializedParams),
    RequestMethodEnum.TEXT_DOCUMENT_DID_OPEN: (
        _text_document_did_open,
        DidOpenTextDocumentParams,
    ),
    RequestMethodEnum.TEXT_DOCUMENT_DID_CHANGE: (
        _text_document_did_change,
        DidChangeTextDocumentParams,
    ),
    RequestMethodEnum.TEXT_DOCUMENT_WILL_SAVE: (
        _text_document_will_save,
        WillSaveTextDocumentParams,
    ),
    RequestMethodEnum.TEXT_DOCUMENT_DID_SAVE: (
        _text_document_did_save,
        DidSaveTextDocumentParams,
    ),
    RequestMethodEnum.TEXT_DOCUMENT_DID_CLOSE: (
        _text_document_did_close,
        DidCloseTextDocumentParams,
    ),
    # RequestMethodEnum.EXIT: lsp_exit,
    # RequestMethodEnum.WINDOW_SHOW_MESSAGE: lsp_window_show_message,
    # RequestMethodEnum.WINDOW_LOG_MESSAGE: lsp_window_log_message,
    # RequestMethodEnum.WINDOW_WORK_DONE_PROGRESS_CANCEL: lsp_window_work_done_progress_cancel,
    # RequestMethodEnum.TELEMETRY_EVENT: lsp_telemetry_event,
    # RequestMethodEnum.WORKSPACE_DID_CHANGE_WORKSPACE_FOLDERS: lsp_workspace_did_change_workspace_folders,
    # RequestMethodEnum.WORKSPACE_DID_CHANGE_CONFIGURATION: lsp_workspace_did_change_configuration,
    # RequestMethodEnum.WORKSPACE_DID_CHANGE_WATCHED_FILES: lsp_workspace_did_change_watched_files,
    # RequestMethodEnum.WORKSPACE_DID_CREATE_FILES: lsp_workspace_did_create_files,
    # RequestMethodEnum.WORKSPACE_DID_RENAME_FILES: lsp_workspace_did_rename_files,
    # RequestMethodEnum.WORKSPACE_DID_DELETE_FILES: lsp_workspace_did_delete_files,
    # RequestMethodEnum.PUBLISH_DIAGNOSTICS: lsp_publish_diagnostics,
    # RequestMethodEnum.LOG_TRACE: lsp_log_trace_notification,
    # RequestMethodEnum.SET_TRACE: lsp_set_trace_notification,
}
