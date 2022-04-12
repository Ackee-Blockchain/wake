from typing import Dict, Callable, Any
import sys

from basic_structures import *
from context import LSPContext
from methods import RequestMethodEnum
'''
Notifications methods just handle what they have to
No return/response necessary
'''

def lsp_initialized(context: LSPContext, params: InitializedParams) -> None:
    pass
    # probably not really useful


def lsp_exit(context: LSPContext, _) -> None:
    if context.shutdown_received:
        sys.exit(0)
    else:
        sys.exit(1)


def lsp_window_show_message(context: LSPContext) -> None:
    raise NotImplementedError()  # TODO


def lsp_window_log_message(context: LSPContext) -> None:
    raise NotImplementedError()  # TODO


def lsp_window_work_done_progress_cancel(context: LSPContext) -> None:
    raise NotImplementedError()  # TODO


def lsp_telemetry_event(context: LSPContext) -> None:
    raise NotImplementedError()  # TODO


def lsp_workspace_did_change_workspace_folders(context: LSPContext, params: DidChangeWorkspaceFoldersParams) -> None:
    raise NotImplementedError()  # TODO


def lsp_workspace_did_change_configuration(context: LSPContext, params: DidChangeConfigurationParams) -> None:
    raise NotImplementedError()  # TODO


def lsp_workspace_did_watched_files(context: LSPContext) -> None:
    raise NotImplementedError()  # TODO


def lsp_workspace_did_create_files(context: LSPContext, params: CreateFilesParams) -> None:
    raise NotImplementedError()  # TODO


def lsp_workspace_did_rename_files(context: LSPContext) -> None:
    raise NotImplementedError()  # TODO


def lsp_workspace_did_delete_files(context: LSPContext) -> None:
    raise NotImplementedError()  # TODO


def lsp_did_open(context: LSPContext) -> None:
    raise NotImplementedError()  # TODO


def lsp_did_change(context: LSPContext) -> None:
    raise NotImplementedError()  # TODO


def lsp_will_save(context: LSPContext) -> None:
    raise NotImplementedError()  # TODO


def lsp_did_save(context: LSPContext) -> None:
    raise NotImplementedError()  # TODO


def lsp_did_close(context: LSPContext) -> None:
    raise NotImplementedError()  # TODO


def lsp_publish_diagnostic(context: LSPContext) -> None:
    raise NotImplementedError()  # TODO
    

def lsp_log_trace_notification(context: LSPContext) -> None:
    raise NotImplementedError()  # TODO


def lsp_set_trace_notification(context: LSPContext) -> None:
    raise NotImplementedError()  # TODO



        
'''
Mapping for all the notifications defined by LSP Specification
https://microsoft.github.io/language-server-protocol/specifications/specification-current/
'''
notification_mapping: Dict[str, Callable[[LSPContext, Any], None]] = {
    RequestMethodEnum.INITIALIZED: lsp_initialized,
    RequestMethodEnum.EXIT: lsp_exit,
    RequestMethodEnum.WINDOW_SHOW_MESSAGE: lsp_window_show_message,
    RequestMethodEnum.WINDOW_LOG_MESSAGE: lsp_window_log_message,
    RequestMethodEnum.WINDOW_WORK_DONE_PROGRESS_CANCEL: lsp_window_work_done_progress_cancel,
    RequestMethodEnum.TELEMETRY_EVENT: lsp_telemetry_event,
    RequestMethodEnum.WORKSPACE_DID_CHANGE_WORKSPACE_FOLDERS: lsp_workspace_did_change_workspace_folders,
    RequestMethodEnum.WORKSPACE_DID_CHANGE_CONFIGURATION: lsp_workspace_did_change_configuration,
    RequestMethodEnum.WORKSPACE_DID_CHANGE_WATCHED_FILES: lsp_workspace_did_watched_files,
    RequestMethodEnum.WORKSPACE_DID_CREATE_FILES: lsp_workspace_did_create_files,
    RequestMethodEnum.WORKSPACE_DID_RENAME_FILES: lsp_workspace_did_rename_files,
    RequestMethodEnum.WORKSPACE_DID_DELETE_FILES: lsp_workspace_did_delete_files,
    RequestMethodEnum.DID_OPEN: lsp_did_open,
    RequestMethodEnum.DID_CHANGE: lsp_did_change,
    RequestMethodEnum.WILL_SAVE: lsp_will_save,
    RequestMethodEnum.DID_SAVE: lsp_did_save,
    RequestMethodEnum.DID_CLOSE: lsp_did_close,
    RequestMethodEnum.PUBLISH_DIAGNOSTICS: lsp_publish_diagnostic,
    RequestMethodEnum.LOG_TRACE_NOTIFICATION: lsp_log_trace_notification,
    RequestMethodEnum.SET_TRACE_NOTIFICATION: lsp_set_trace_notification,
}