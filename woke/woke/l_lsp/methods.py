from strenum import StrEnum


class RequestMethodEnum(StrEnum):
    # General
    INITIALIZE = "initialize"
    INITIALIZED = "initialized"  # Notification
    SHUTDOWN = "shutdown"
    EXIT = "exit"  # Notification

    # Window
    WINDOW_SHOW_MESSAGE = "window/showMessage"  # Notification
    WINDOW_SHOW_MESSAGE_REQUEST = "window/showMessageRequest"
    WINDOW_SHOW_DOCUMENT = "window/showDocument"
    WINDOW_LOG_MESSAGE = "window/logMessage"  # Notification
    WINDOW_WORK_DONE_PROGRESS_CREATE = "window/workDoneProgress/create"
    WINDOW_WORK_DONE_PROGRESS_CANCEL = "window/workDoneProgress/cancel"  # Notification

    # Telemetry
    TELEMETRY_EVENT = "telemetry/event"  # Notification

    # Client
    CLIENT_REGISTER_CAPABILITY = "client/registerCapability"
    CLIENT_UNREGISTER_CAPABILITY = "client/unregisterCapability"

    # Workspace
    WORKSPACE_WORKSPACE_FOLDERS = "workspace/workspaceFolders"
    WORKSPACE_DID_CHANGE_WORKSPACE_FOLDERS = (
        "workspace/didChangeWorkspaceFolders"  # Notification
    )
    WORKSPACE_DID_CHANGE_CONFIGURATION = (
        "workspace/didChangeConfiguration"  # Notification
    )
    WORKSPACE_CONFIGURATION = "workspace/configuration"
    WORKSPACE_DID_CHANGE_WATCHED_FILES = (
        "workspace/didChangeWatchedFiles"  # Notification
    )
    WORKSPACE_SYMBOL = "workspace/symbol"
    WORKSPACE_SYMBOL_RESOLVE = "workspaceSymbol/resolve"
    WORKSPACE_EXECUTE_COMMAND = "workspace/executeCommand"
    WORKSPACE_APPLY_EDIT = "workspace/applyEdit"

    # File Operations
    WORKSPACE_WILL_CREATE_FILES = "workspace/willCreateFiles"
    WORKSPACE_DID_CREATE_FILES = "workspace/didCreateFiles"  # Notification
    WORKSPACE_WILL_RENAME_FILES = "workspace/willRenameFiles"
    WORKSPACE_DID_RENAME_FILES = "workspace/didRenameFiles"  # Notification
    WORKSPACE_WILL_DELETE_FILES = "workspace/willDeleteFiles"
    WORKSPACE_DID_DELETE_FILES = "workspace/didDeleteFiles"  # Notification

    # Text Synchronization
    DID_OPEN = "textDocument/didOpen"  # Notification
    DID_CHANGE = "textDocument/didChange"  # Notification
    WILL_SAVE = "textDocument/willSave"  # Notification
    WILL_SAVE_WAIT_UNTIL = "textDocument/willSaveWaitUntil"
    DID_SAVE = "textDocument/didSave"  # Notification
    DID_CLOSE = "textDocument/didClose"  # Notification

    # Diagnostics
    PUBLISH_DIAGNOSTICS = "textDocument/publishDiagnostics"  # Notification

    # Language Features
    COMPLETION = "textDocument/completion"
    COMPLETION_ITEM_RESOLVE = "completionItem/resolve"
    HOVER = "textDocument/hover"
    SIGNATURE_HELP = "textDocument/signatureHelp"
    DECLARATION = "textDocument/declaration"
    DEFINITION = "textDocument/definition"
    TYPE_DEFINITION = "textDocument/typeDefinition"
    IMPLEMENTATION = "textDocument/implementation"
    REFERENCES = "textDocument/references"
    DOCUMENT_HIGHLIGHT = "textDocument/documentHighlight"
    DOCUMENT_SYMBOL = "textDocument/documentSymbol"
    CODE_ACTION = "textDocument/codeAction"
    CODE_ACTION_RESOLVE = "codeAction/resolve"
    CODE_LENS = "textDocument/codeLens"
    CODE_LENS_RESOLVE = "codeLens/resolve"
    WORKSPACE_CODE_LENS_REFRESH = "workspace/codeLens/refresh"
    DOCUMENT_LINK = "textDocument/documentLink"
    DOCUMENT_LINK_RESOLVE = "documentLink/resolve"
    DOCUMENT_COLOR = "textDocument/documentColor"
    COLOR_PRESENTATION = "textDocument/colorPresentation"
    FORMATTING = "textDocument/formatting"
    RANGE_FORMATTING = "textDocument/rangeFormatting"
    ON_TYPE_FORMATTING = "textDocument/onTypeFormatting"
    RENAME = "textDocument/rename"
    PREPARE_RENAME = "textDocument/prepareRename"
    FOLDING_RANGE = "textDocument/foldingRange"
    SELECTION_RANGE = "textDocument/selectionRange"
    PREPARE_CALL_HIERARCHY_ = "textDocument/prepareCallHierarchy"
    CALL_HIERARCHY_INCOMING_CALLS = "callHierarchy/incomingCalls"
    CALL_HIERARCHY_OUTGOING_CALLS = "callHierarchy/outgoingCalls"
    SEMANTIC_TOKENS = "textDocument/semanticTokens"
    SEMANTIC_TOKENS_FULL = "textDocument/semanticTokens/full"
    SEMANTIC_TOKENS_FULL_DELTA = "textDocument/semanticTokens/full/delta"
    SEMANTIC_TOKENS_RANGE = "textDocument/semanticTokens/range"
    SEMANTIC_TOKENS_REFRESH = "workspace/semanticTokens/refresh"
    LINKED_EDITING_RANGE = "textDocument/linkedEditingRange"
    MONIKER = "textDocument/moniker"

    # Other
    CANCEL_REQUEST = "$/cancelRequest"
    PROGRESS_NOTIFICATION = "$/progress"
    LOG_TRACE_NOTIFICATION = "$/logTrace"  # Notification
    SET_TRACE_NOTIFICATION = "$/setTrace"  # Notification
