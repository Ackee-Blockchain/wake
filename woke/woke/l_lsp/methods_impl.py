from typing import Dict, Callable
from pathlib import Path
from urllib.parse import quote, unquote
import sys
import os 

#from woke.a_config import WokeConfig
from basic_structures import *
from context import LSPContext
from methods import RequestMethodEnum

def uri_to_path(uri: str) -> str:
    if not uri.startswith("file://"):
        return os.path.abspath(uri)
    if os.name == "nt":
        _, path = uri.split("file:///", 1)
    else:
        _, path = uri.split("file://", 1)
    return str(Path(unquote(path)).resolve())


def lsp_initialize(context: LSPContext, params: InitializeParams) -> InitializeResult:
    if params.worskpace_folders is not None:
        if len(params.workspace_folders) != 1:
            raise InitializeError("Exactly one workspace directory must be provided.", retry=False)
        path = uri_to_path(params.worskpace_folders[0].uri)
        #print(path)
    elif params.root_uri is not None:
        path = uri_to_path(params.root_uri)
    elif params.root_path is not None:
        path = Path(params.root_path).resolve(strict=True)
    else:
        raise InitializeError("Workspace/root directory was not specified.", retry=False)
    
    context.woke_config = WokeConfig(project_root_path=path)
    #return InitializeResult(server_capabilities)


def lsp_initialized(context: LSPContext, params: InitializedParams) -> None:
    pass
    # probably not really useful


def lsp_shutdown(context: LSPContext, _) -> None:
    context.shutdown_received = True


def lsp_exit(context: LSPContext, _) -> None:
    if context.shutdown_received:
        sys.exit(0)
    else:
        sys.exit(1)


def lsp_set_trace(context: LSPContext, params: SetTraceParams) -> None:
    context.trace_value = params.value


def lsp_window_progress_cancel(context: LSPContext, params: WorkDoneProgressCancelParams) -> None:
    raise NotImplementedError()  # TODO


def lsp_workspace_symbol(context: LSPContext, params: WorkspaceSymbolParams) -> Union[List[SymbolInformation], List[WorkspaceSymbol], None]:
    raise NotImplementedError()  # TODO


def lsp_workspace_symbol_resolve(context: LSPContext, params: WorkspaceSymbol) -> WorkspaceSymbol:
    raise NotImplementedError()  # TODO


def lsp_workspace_will_create_files(context: LSPContext, params: CreateFilesParams) -> Optional[WorkspaceEdit]:
    raise NotImplementedError()  # TODO


method_mapping: Dict[str, Callable[[LSPContext, Any], Any]] = {
    RequestMethodEnum.INITIALIZE: lsp_initialize,
    RequestMethodEnum.INITIALIZED: lsp_initialized,
    RequestMethodEnum.SHUTDOWN: lsp_shutdown,
    RequestMethodEnum.EXIT: lsp_exit,
    RequestMethodEnum.SET_TRACE_NOTIFICATION: lsp_set_trace,
    RequestMethodEnum.WINDOW_WORK_DONE_PROGRESS_CANCEL: lsp_window_progress_cancel,
    RequestMethodEnum.WORKSPACE_SYMBOL: lsp_workspace_symbol,
    RequestMethodEnum.WORKSPACE_SYMBOL_RESOLVE: lsp_workspace_symbol_resolve,
    RequestMethodEnum.WORKSPACE_WILL_CREATE_FILES: lsp_workspace_will_create_files,
}