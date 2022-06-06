import os
import sys
from pathlib import Path
from typing import Dict, Callable
from urllib.parse import unquote

from woke.a_config import WokeConfig
from .basic_structures import *
from .context import LSPContext
from .enums import TraceValueEnum
from .methods import RequestMethodEnum


def uri_to_path(uri: str) -> str:
    if not uri.startswith("file://"):
        return os.path.abspath(uri)
    if os.name == "nt":
        _, path = uri.split("file:///", 1)
    else:
        _, path = uri.split("file://", 1)
    return str(Path(unquote(path)).resolve())


######################
## client -> server ##
######################
def lsp_initialize(context: LSPContext, params: InitializeParams) -> InitializeResult:
    if params.worskpace_folders is not None:
        if len(params.workspace_folders) != 1:
            raise InitializeError(
                "Exactly one workspace directory must be provided.", retry=False
            )
        path = uri_to_path(params.worskpace_folders[0].uri)
        # print(path)
    elif params.root_uri is not None:
        path = uri_to_path(params.root_uri)
    elif params.root_path is not None:
        path = Path(params.root_path).resolve(strict=True)
    else:
        raise InitializeError(
            "Workspace/root directory was not specified.", retry=False
        )

    context.woke_config = WokeConfig(project_root_path=path)
    return InitializeResult(context.server_capabilities)


def lsp_shutdown(context: LSPContext, _) -> None:
    context.shutdown_received = True


def lsp_workspace_symbol(
    context: LSPContext, params: WorkspaceSymbolParams
) -> Union[List[SymbolInformation], List[WorkspaceSymbol], None]:
    raise NotImplementedError()  # TODO


def lsp_workspace_symbol_resolve(
    context: LSPContext, params: WorkspaceSymbol
) -> WorkspaceSymbol:
    raise NotImplementedError()  # TODO


def lsp_workspace_execute_command(context: LSPContext):
    raise NotImplementedError()  # TODO


def lsp_workspace_will_create_files(
    context: LSPContext, params: CreateFilesParams
) -> Optional[WorkspaceEdit]:
    raise NotImplementedError()  # TODO


def lsp_workspace_will_rename_files(context: LSPContext):
    raise NotImplementedError()  # TODO


def lsp_workspace_will_delete_files(context: LSPContext):
    raise NotImplementedError()  # TODO


def lsp_will_save_wait_until(context: LSPContext):
    raise NotImplementedError()  # TODO


######################
## server -> client ##
######################


def lsp_window_show_message_request(context: LSPContext):
    raise NotImplementedError()  # TODO


def lsp_window_show_document(context: LSPContext):
    raise NotImplementedError()  # TODO


def lsp_window_work_done_progress_create(context: LSPContext):
    raise NotImplementedError()  # TODO


def lsp_client_register_capability(context: LSPContext):
    raise NotImplementedError()  # TODO


def lsp_client_unregister_capability(context: LSPContext):
    raise NotImplementedError()  # TODO


def lsp_workspace_folders(context: LSPContext):
    raise NotImplementedError()  # TODO


def lsp_workspace_configuration(context: LSPContext):
    raise NotImplementedError()  # TODO


def lsp_workspace_apply_edit(context: LSPContext):
    raise NotImplementedError()  # TODO


"""
Mapping for all the requests defined by LSP Specification
https://microsoft.github.io/language-server-protocol/specifications/specification-current/
"""
method_mapping: Dict[str, Callable[[LSPContext, Any], Any]] = {
    RequestMethodEnum.INITIALIZE: lsp_initialize,
    RequestMethodEnum.SHUTDOWN: lsp_shutdown,
    RequestMethodEnum.WINDOW_SHOW_MESSAGE_REQUEST: lsp_window_show_message_request,
    RequestMethodEnum.WINDOW_SHOW_DOCUMENT: lsp_window_show_document,
    RequestMethodEnum.WINDOW_WORK_DONE_PROGRESS_CREATE: lsp_window_work_done_progress_create,
    RequestMethodEnum.CLIENT_REGISTER_CAPABILITY: lsp_client_register_capability,
    RequestMethodEnum.CLIENT_UNREGISTER_CAPABILITY: lsp_client_unregister_capability,
    RequestMethodEnum.WORKSPACE_WORKSPACE_FOLDERS: lsp_workspace_folders,
    RequestMethodEnum.WORKSPACE_CONFIGURATION: lsp_workspace_configuration,
    RequestMethodEnum.WORKSPACE_SYMBOL: lsp_workspace_symbol,
    RequestMethodEnum.WORKSPACE_SYMBOL_RESOLVE: lsp_workspace_symbol_resolve,
    RequestMethodEnum.WORKSPACE_EXECUTE_COMMAND: lsp_workspace_execute_command,
    RequestMethodEnum.WORKSPACE_APPLY_EDIT: lsp_workspace_apply_edit,
    RequestMethodEnum.WORKSPACE_WILL_CREATE_FILES: lsp_workspace_will_create_files,
    RequestMethodEnum.WORKSPACE_WILL_RENAME_FILES: lsp_workspace_will_rename_files,
    RequestMethodEnum.WORKSPACE_WILL_DELETE_FILES: lsp_workspace_will_delete_files,
    RequestMethodEnum.WILL_SAVE_WAIT_UNTIL: lsp_will_save_wait_until,
    # RequestMethodEnum.CANCEL_REQUEST: lsp_cancel_request,
    # RequestMethodEnum.PROGRESS_NOTIFICATION: lsp_progrss_notification,
}
