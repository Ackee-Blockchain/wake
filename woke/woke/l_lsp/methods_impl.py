import logging
from typing import Dict, Callable, Tuple, Type

from woke.a_config import WokeConfig
from .common_structures import *
from .context import LspContext
from .exceptions import LspError
from .methods import RequestMethodEnum
from .protocol_structures import ErrorCodes


logger = logging.getLogger(__name__)


def uri_to_path(uri: str) -> str:
    if not uri.startswith("file://"):
        return os.path.abspath(uri)
    if os.name == "nt":
        _, path = uri.split("file:///", 1)
    else:
        _, path = uri.split("file://", 1)
    return str(Path(unquote(path)).resolve())


def _initialize(context: LspContext, params: InitializeParams) -> InitializeResult:
    if context.initialized:
        raise LspError(ErrorCodes.InvalidRequest, "Server already initialized")

    if params.workspace_folders is not None:
        if len(params.workspace_folders) != 1:
            raise LspError(
                ErrorCodes.RequestFailed,
                "Exactly one workspace directory must be provided.",
                InitializeError(retry=False),
            )
        path = uri_to_path(params.workspace_folders[0].uri)
    elif params.root_uri is not None:
        path = uri_to_path(params.root_uri)
    elif params.root_path is not None:
        path = Path(params.root_path).resolve(strict=True)
    else:
        raise LspError(
            ErrorCodes.RequestFailed,
            "Exactly one workspace directory must be provided.",
            InitializeError(retry=False),
        )

    context.create_compilation_thread()
    context.initialized = True

    server_capabilities = ServerCapabilities(
        position_encoding=PositionEncodingKind.UTF16,
        text_document_sync=TextDocumentSyncOptions(
            open_close=True, change=TextDocumentSyncKind.INCREMENTAL
        ),
        # diagnostic_provider=DiagnosticRegistrationOptions(
        # document_selector=[DocumentFilter(language="solidity")],
        # inter_file_dependencies=True,
        # workspace_diagnostics=True,
        # ),
    )
    return InitializeResult(capabilities=server_capabilities, server_info=None)


def _shutdown(context: LspContext, _) -> None:
    context.shutdown_received = True


def lsp_workspace_symbol(
    context: LspContext, params: WorkspaceSymbolParams
) -> Union[List[SymbolInformation], List[WorkspaceSymbol], None]:
    raise NotImplementedError()  # TODO


def lsp_workspace_symbol_resolve(
    context: LspContext, params: WorkspaceSymbol
) -> WorkspaceSymbol:
    raise NotImplementedError()  # TODO


def lsp_workspace_execute_command(context: LspContext):
    raise NotImplementedError()  # TODO


def lsp_workspace_will_create_files(
    context: LspContext, params: CreateFilesParams
) -> Optional[WorkspaceEdit]:
    raise NotImplementedError()  # TODO


def lsp_workspace_will_rename_files(context: LspContext):
    raise NotImplementedError()  # TODO


def lsp_workspace_will_delete_files(context: LspContext):
    raise NotImplementedError()  # TODO


def lsp_will_save_wait_until(context: LspContext):
    raise NotImplementedError()  # TODO


######################
## server -> client ##
######################


def lsp_window_show_message_request(context: LspContext):
    raise NotImplementedError()  # TODO


def lsp_window_show_document(context: LspContext):
    raise NotImplementedError()  # TODO


def lsp_window_work_done_progress_create(context: LspContext):
    raise NotImplementedError()  # TODO


def lsp_client_register_capability(context: LspContext):
    raise NotImplementedError()  # TODO


def lsp_client_unregister_capability(context: LspContext):
    raise NotImplementedError()  # TODO


def lsp_workspace_folders(context: LspContext):
    raise NotImplementedError()  # TODO


def lsp_workspace_configuration(context: LspContext):
    raise NotImplementedError()  # TODO


def lsp_workspace_apply_edit(context: LspContext):
    raise NotImplementedError()  # TODO


def handle_client_to_server_method(
    context: LspContext, request: str, params: Optional[Dict]
) -> Any:
    try:
        m, params_type = _method_mapping[request]
    except KeyError:
        logger.error(f"Incoming request type '{request}' not implemented.")
        raise NotImplementedError()

    if params_type is not None:
        return m(context, params_type.parse_obj(params))
    else:
        return m(context, None)


"""
Mapping for all the requests defined by LSP Specification
https://microsoft.github.io/language-server-protocol/specifications/specification-current/
"""
_method_mapping: Dict[
    str, Tuple[Callable[[LspContext, Any], Any], Optional[Type[LspModel]]]
] = {
    RequestMethodEnum.INITIALIZE: (_initialize, InitializeParams),
    RequestMethodEnum.SHUTDOWN: (_shutdown, None),
    # RequestMethodEnum.WINDOW_SHOW_MESSAGE_REQUEST: (lsp_window_show_message_request, ShowMessageRequestParams),
    # RequestMethodEnum.WINDOW_SHOW_DOCUMENT: (lsp_window_show_document, ShowDocumentParams),
    # RequestMethodEnum.WINDOW_WORK_DONE_PROGRESS_CREATE: (lsp_window_work_done_progress_create, WorkDoneProgressCreateParams),
    # RequestMethodEnum.TEXT_DOCUMENT_WILL_SAVE_WAIT_UNTIL: (lsp_will_save_wait_until, WillSaveTextDocumentParams),
    # RequestMethodEnum.CLIENT_REGISTER_CAPABILITY: (lsp_client_register_capability, RegistrationParams),
    # RequestMethodEnum.CLIENT_UNREGISTER_CAPABILITY: lsp_client_unregister_capability,
    # RequestMethodEnum.WORKSPACE_WORKSPACE_FOLDERS: lsp_workspace_folders,
    # RequestMethodEnum.WORKSPACE_CONFIGURATION: lsp_workspace_configuration,
    # RequestMethodEnum.WORKSPACE_SYMBOL: lsp_workspace_symbol,
    # RequestMethodEnum.WORKSPACE_SYMBOL_RESOLVE: lsp_workspace_symbol_resolve,
    # RequestMethodEnum.WORKSPACE_EXECUTE_COMMAND: lsp_workspace_execute_command,
    # RequestMethodEnum.WORKSPACE_APPLY_EDIT: lsp_workspace_apply_edit,
    # RequestMethodEnum.WORKSPACE_WILL_CREATE_FILES: lsp_workspace_will_create_files,
    # RequestMethodEnum.WORKSPACE_WILL_RENAME_FILES: lsp_workspace_will_rename_files,
    # RequestMethodEnum.WORKSPACE_WILL_DELETE_FILES: lsp_workspace_will_delete_files,
    # RequestMethodEnum.CANCEL_REQUEST: lsp_cancel_request,
    # RequestMethodEnum.PROGRESS_NOTIFICATION: lsp_progrss_notification,
}
