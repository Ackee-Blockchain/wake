import enum


class RequestMethodEnum(str, enum.Enum):
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
    WORKSPACE_SYMBOL = "workspace/symbol"
    WORKSPACE_SYMBOL_RESOLVE = "workspaceSymbol/resolve"
    WORKSPACE_CONFIGURATION = "workspace/configuration"
    WORKSPACE_DID_CHANGE_CONFIGURATION = (
        "workspace/didChangeConfiguration"  # Notification
    )
    WORKSPACE_WORKSPACE_FOLDERS = "workspace/workspaceFolders"
    WORKSPACE_DID_CHANGE_WORKSPACE_FOLDERS = (
        "workspace/didChangeWorkspaceFolders"  # Notification
    )
    WORKSPACE_EXECUTE_COMMAND = "workspace/executeCommand"
    WORKSPACE_APPLY_EDIT = "workspace/applyEdit"
    WORKSPACE_CODE_LENS_REFRESH = "workspace/codeLens/refresh"
    WORKSPACE_DIAGNOSTIC = "workspace/diagnostic"
    WORKSPACE_DIAGNOSTIC_REFRESH = "workspace/diagnostic/refresh"

    # File Operations
    WORKSPACE_WILL_CREATE_FILES = "workspace/willCreateFiles"
    WORKSPACE_DID_CREATE_FILES = "workspace/didCreateFiles"  # Notification
    WORKSPACE_WILL_RENAME_FILES = "workspace/willRenameFiles"
    WORKSPACE_DID_RENAME_FILES = "workspace/didRenameFiles"  # Notification
    WORKSPACE_WILL_DELETE_FILES = "workspace/willDeleteFiles"
    WORKSPACE_DID_DELETE_FILES = "workspace/didDeleteFiles"  # Notification
    WORKSPACE_DID_CHANGE_WATCHED_FILES = (
        "workspace/didChangeWatchedFiles"  # Notification
    )

    # Text Synchronization
    TEXT_DOCUMENT_DID_OPEN = "textDocument/didOpen"  # Notification
    TEXT_DOCUMENT_DID_CHANGE = "textDocument/didChange"  # Notification
    TEXT_DOCUMENT_WILL_SAVE = "textDocument/willSave"  # Notification
    TEXT_DOCUMENT_WILL_SAVE_WAIT_UNTIL = "textDocument/willSaveWaitUntil"
    TEXT_DOCUMENT_DID_SAVE = "textDocument/didSave"  # Notification
    TEXT_DOCUMENT_DID_CLOSE = "textDocument/didClose"  # Notification

    # Notebook Document
    NOTEBOOK_DOCUMENT_DID_OPEN = "notebookDocument/didOpen"  # Notification
    NOTEBOOK_DOCUMENT_DID_CHANGE = "notebookDocument/didChange"  # Notification
    NOTEBOOK_DOCUMENT_DID_SAVE = "notebookDocument/didSave"  # Notification
    NOTEBOOK_DOCUMENT_DID_CLOSE = "notebookDocument/didClose"  # Notification

    # Language Features
    DECLARATION = "textDocument/declaration"
    DEFINITION = "textDocument/definition"
    TYPE_DEFINITION = "textDocument/typeDefinition"
    IMPLEMENTATION = "textDocument/implementation"
    REFERENCES = "textDocument/references"
    PREPARE_CALL_HIERARCHY = "textDocument/prepareCallHierarchy"
    CALL_HIERARCHY_INCOMING_CALLS = "callHierarchy/incomingCalls"
    CALL_HIERARCHY_OUTGOING_CALLS = "callHierarchy/outgoingCalls"
    PREPARE_TYPE_HIERARCHY = "textDocument/prepareTypeHierarchy"
    TYPE_HIERARCHY_SUPERTYPES = "typeHierarchy/supertypes"
    TYPE_HIERARCHY_SUBTYPES = "typeHierarchy/subtypes"
    DOCUMENT_HIGHLIGHT = "textDocument/documentHighlight"
    DOCUMENT_LINK = "textDocument/documentLink"
    DOCUMENT_LINK_RESOLVE = "documentLink/resolve"
    HOVER = "textDocument/hover"
    CODE_LENS = "textDocument/codeLens"
    CODE_LENS_RESOLVE = "codeLens/resolve"
    FOLDING_RANGE = "textDocument/foldingRange"
    SELECTION_RANGE = "textDocument/selectionRange"
    DOCUMENT_SYMBOL = "textDocument/documentSymbol"
    SEMANTIC_TOKENS = "textDocument/semanticTokens"  # TODO: only used for registration
    SEMANTIC_TOKENS_FULL = "textDocument/semanticTokens/full"
    SEMANTIC_TOKENS_FULL_DELTA = "textDocument/semanticTokens/full/delta"
    SEMANTIC_TOKENS_RANGE = "textDocument/semanticTokens/range"
    SEMANTIC_TOKENS_REFRESH = "workspace/semanticTokens/refresh"
    INLAY_HINT = "textDocument/inlayHint"
    INLAY_HINT_RESOLVE = "inlayHint/resolve"
    INLAY_HINT_REFRESH = "workspace/inlayHint/refresh"
    INLINE_VALUE = "textDocument/inlineValue"
    INLINE_VALUE_REFRESH = "textDocument/inlineValue/refresh"
    MONIKER = "textDocument/moniker"
    COMPLETION = "textDocument/completion"
    COMPLETION_ITEM_RESOLVE = "completionItem/resolve"
    PUBLISH_DIAGNOSTICS = "textDocument/publishDiagnostics"  # Notification
    DIAGNOSTIC = "textDocument/diagnostic"
    SIGNATURE_HELP = "textDocument/signatureHelp"
    CODE_ACTION = "textDocument/codeAction"
    CODE_ACTION_RESOLVE = "codeAction/resolve"
    DOCUMENT_COLOR = "textDocument/documentColor"
    COLOR_PRESENTATION = "textDocument/colorPresentation"
    FORMATTING = "textDocument/formatting"
    RANGE_FORMATTING = "textDocument/rangeFormatting"
    ON_TYPE_FORMATTING = "textDocument/onTypeFormatting"
    RENAME = "textDocument/rename"
    PREPARE_RENAME = "textDocument/prepareRename"
    LINKED_EDITING_RANGE = "textDocument/linkedEditingRange"

    # Other
    CANCEL_REQUEST = "$/cancelRequest"
    PROGRESS = "$/progress"
    LOG_TRACE = "$/logTrace"  # Notification
    SET_TRACE = "$/setTrace"  # Notification
