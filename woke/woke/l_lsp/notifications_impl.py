import logging
import sys
from typing import Dict, Callable, Tuple, Type

from .basic_structures import *
from .context import LspContext
from .enums import TraceValueEnum
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


def lsp_exit(context: LspContext, _) -> None:
    print("Stop listening")
    if context.shutdown_received:
        sys.exit(0)
    else:
        sys.exit(1)


def lsp_window_show_message(context: LspContext, params: dict) -> None:
    """
    Display particular message in the user interface
    """
    show_message_params = ShowMessageParams.parse_obj(t_dict(params))
    raise NotImplementedError()  # TODO


def lsp_window_work_done_progress_cancel(context: LspContext, params: dict) -> None:
    work_done_progress_params = WorkDoneProgressCancelParams.parse_obj(t_dict(params))
    raise NotImplementedError()  # TODO


def lsp_workspace_did_change_workspace_folders(
    context: LspContext, params: dict
) -> None:
    did_change_workspace_params = DidChangeWorkspaceFoldersParams.parse_obj(
        t_dict(params)
    )
    raise NotImplementedError()  # TODO


def lsp_workspace_did_change_configuration(context: LspContext, params: dict) -> None:
    did_change_config_params = DidChangeConfigurationParams.parse_obj(t_dict(params))
    raise NotImplementedError()  # TODO


def lsp_workspace_did_change_watched_files(context: LspContext, params: dict) -> None:
    did_change_watcher_params = DidChangeWatchedParams.parse_obj(t_dict(params))
    raise NotImplementedError()  # TODO


def lsp_workspace_did_create_files(context: LspContext, params: dict) -> None:
    did_create_params = CreateFilesParams.parse_obj(t_dict(params))
    raise NotImplementedError()  # TODO


def lsp_workspace_did_rename_files(
    context: LspContext, params: RenameFilesParams
) -> None:
    did_rename_params = RenameFilesParams.parse_obj(t_dict(params))
    raise NotImplementedError()  # TODO


def lsp_workspace_did_delete_files(context: LspContext, params: dict) -> None:
    did_delete_params = DeleteFilesParams.parse_obj(t_dict(params))
    raise NotImplementedError()  # TODO


def _text_document_did_open(
    context: LspContext, params: DidOpenTextDocumentParams
) -> None:
    context.compiler.file_changes_queue.put(params)


def _text_document_did_change(
    context: LspContext, params: DidChangeTextDocumentParams
) -> None:
    context.compiler.file_changes_queue.put(params)


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
    pass


def lsp_set_trace_notification(context: LspContext, params: dict) -> None:
    set_trace_params = SetTraceParams.parse_obj(t_dict(params))
    context.trace_value = TraceValueEnum(set_trace_params.value)


######################
#  server -> client  #
######################


def lsp_window_log_message(context: LspContext, params: dict) -> None:
    window_log_params = LogMessageParams.parse_obj(t_dict(params))
    raise NotImplementedError()  # TODO


def lsp_telemetry_event(context: LspContext, params: Any) -> None:
    raise NotImplementedError()  # TODO


def lsp_publish_diagnostics(context: LspContext, params: dict) -> None:
    publish_diagnostic_params = PublishDiagnosticsParams.parse_obj(t_dict(params))
    raise NotImplementedError()  # TODO


def lsp_log_trace_notification(context: LspContext, params: dict) -> None:
    log_trace_params = LogTraceParams.parse_obj(t_dict(params))
    raise NotImplementedError()  # TODO


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
