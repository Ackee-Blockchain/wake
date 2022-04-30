import sys
from typing import Dict, Callable

from .basic_structures import *
from .context import LSPContext
from .enums import TraceValueEnum
from .methods import RequestMethodEnum

"""
Notifications methods just handle what they have to
No return/response necessary
"""

######################
#  client -> server  #
######################


def lsp_initialized(context: LSPContext, params: InitializedParams) -> None:
    # probably not really useful
    pass


def lsp_exit(context: LSPContext, _) -> None:
    if context.shutdown_received:
        sys.exit(0)
    else:
        sys.exit(1)


def lsp_window_show_message(context: LSPContext, params: ShowMessageParams) -> None:
    """
    Display particular message in the user interface
    """
    raise NotImplementedError()  # TODO


def lsp_window_work_done_progress_cancel(
    context: LSPContext, params: WorkDoneProgressCancelParams
) -> None:
    raise NotImplementedError()  # TODO


def lsp_workspace_did_change_workspace_folders(
    context: LSPContext, params: DidChangeWorkspaceFoldersParams
) -> None:
    raise NotImplementedError()  # TODO


def lsp_workspace_did_change_configuration(
    context: LSPContext, params: DidChangeConfigurationParams
) -> None:
    raise NotImplementedError()  # TODO


def lsp_workspace_did_change_watched_files(context: LSPContext, params: DidChangeWatchedParams) -> None:
    raise NotImplementedError()  # TODO


def lsp_workspace_did_create_files(
    context: LSPContext, params: CreateFilesParams
) -> None:
    raise NotImplementedError()  # TODO


def lsp_workspace_did_rename_files(context: LSPContext, params: RenameFilesParams) -> None:
    raise NotImplementedError()  # TODO


def lsp_workspace_did_delete_files(context: LSPContext, params: DeleteFilesParams) -> None:
    raise NotImplementedError()  # TODO


def lsp_did_open(context: LSPContext, params: DidOpenTextDocumentParams) -> None:
    """
    Update workspace with new document
    """
    """
    if params.text_document is not None:
        document = params.text_document
        context.workspace[document.uri] = document
    """


def lsp_did_change(context: LSPContext, params: DidChangeTextDocumentParams) -> None:
    """
    Update worskpace document
    """
    """
    if params.text_document is not None:
        uri = params.text_document.uri
        if context.workspace[uri] is not None:
            version = params.text_document.version
            changes = params.content_changes
            context.update_workspace(uri, version, changes)
    """
    raise NotImplementedError()  # TODO


def lsp_will_save(context: LSPContext, params: WillSaveTextDocumentParams) -> None:
    raise NotImplementedError()  # TODO


def lsp_did_save(context: LSPContext, params: DidSaveTextDocumentParams) -> None:
    raise NotImplementedError()  # TODO


def lsp_did_close(context: LSPContext, params: DidCloseTextDocumentParams) -> None:
    raise NotImplementedError()  # TODO


def lsp_set_trace_notification(context: LSPContext, params: SetTraceParams) -> None:
    context.trace_value = TraceValueEnum(params.value)


######################
#  server -> client  #
######################


def lsp_window_log_message(context: LSPContext, params: LogMessageParams) -> None:
    raise NotImplementedError()  # TODO


def lsp_telemetry_event(context: LSPContext, params: Any) -> None:
    raise NotImplementedError()  # TODO


def lsp_publish_diagnostics(context: LSPContext, params: PublishDiagnosticsParams) -> None:
    raise NotImplementedError()  # TODO


def lsp_log_trace_notification(context: LSPContext, params: LogTraceParams) -> None:
    raise NotImplementedError()  # TODO


"""
Mapping for all the notifications defined by LSP Specification
https://microsoft.github.io/language-server-protocol/specifications/specification-current/
"""
notification_mapping: Dict[str, Callable[[LSPContext, Any], None]] = {
    RequestMethodEnum.INITIALIZED: lsp_initialized,
    RequestMethodEnum.EXIT: lsp_exit,
    RequestMethodEnum.WINDOW_SHOW_MESSAGE: lsp_window_show_message,
    RequestMethodEnum.WINDOW_LOG_MESSAGE: lsp_window_log_message,
    RequestMethodEnum.WINDOW_WORK_DONE_PROGRESS_CANCEL: lsp_window_work_done_progress_cancel,
    RequestMethodEnum.TELEMETRY_EVENT: lsp_telemetry_event,
    RequestMethodEnum.WORKSPACE_DID_CHANGE_WORKSPACE_FOLDERS: lsp_workspace_did_change_workspace_folders,
    RequestMethodEnum.WORKSPACE_DID_CHANGE_CONFIGURATION: lsp_workspace_did_change_configuration,
    RequestMethodEnum.WORKSPACE_DID_CHANGE_WATCHED_FILES: lsp_workspace_did_change_watched_files,
    RequestMethodEnum.WORKSPACE_DID_CREATE_FILES: lsp_workspace_did_create_files,
    RequestMethodEnum.WORKSPACE_DID_RENAME_FILES: lsp_workspace_did_rename_files,
    RequestMethodEnum.WORKSPACE_DID_DELETE_FILES: lsp_workspace_did_delete_files,
    RequestMethodEnum.DID_OPEN: lsp_did_open,
    RequestMethodEnum.DID_CHANGE: lsp_did_change,
    RequestMethodEnum.WILL_SAVE: lsp_will_save,
    RequestMethodEnum.DID_SAVE: lsp_did_save,
    RequestMethodEnum.DID_CLOSE: lsp_did_close,
    RequestMethodEnum.PUBLISH_DIAGNOSTICS: lsp_publish_diagnostics,
    RequestMethodEnum.LOG_TRACE_NOTIFICATION: lsp_log_trace_notification,
    RequestMethodEnum.SET_TRACE_NOTIFICATION: lsp_set_trace_notification,
}
