import re
from enum import Enum, IntEnum
from typing import Any, List, Optional, Union, NewType

from .lsp_data_model import LspModel

DocumentUri = NewType("URI", str)
URI = NewType("URI", str)
ChangeAnnotationIdentifier = NewType("ChangeAnnotationIdentifier", str)
ProgressToken = Union[int, str]
TraceValue = NewType("Trace", str)  # NewType(Union["off","message","verbose"], str)


def to_snake(s):
    return re.sub("([A-Z]\w+$)", "_\\1", s).lower()


def t_dict(d):
    if isinstance(d, list):
        return [t_dict(i) if isinstance(i, (dict, list)) else i for i in d]
    return {
        to_snake(a): t_dict(b) if isinstance(b, (dict, list)) else b
        for a, b in d.items()
    }


class RegularExpressionsClientCapabilities(LspModel):
    engine: str
    """
    The engine's name.
    """
    version: Optional[str]
    """
    The engine's version.
    """


class Position(LspModel):
    line: int
    """
    Position in a document (zero-based).
    """
    character: int
    """
    Character offset on a line in a document (zero-based).between the `character` and `character + 1`.
    """


class Range(LspModel):
    start: Position
    """
    The range's start position.
    """
    end: Position
    """
    The range's end position.
    """


class Location(LspModel):
    """
    Represents a location inside a resource, such as a line inside a text file.
    """

    uri: DocumentUri
    range: Range


class LocationLink(LspModel):
    origin_selection_range: Optional[Range]
    """
    Span of the origin of this link.
    Used as the underlined span for mouse interaction.
    Defaults to the word range at the mouse position.
    """
    target_uri: str
    """
     The target resource identifier of this link.
    """
    target_range: Range
    """
    The full target range of this link.
    """
    target_selection_range: Range
    """
    The range that should be selected and revealed when this link is being followed,
    e.g the name of a function. Must be contained by the the `target_Range`.
    """


class DiagnosticSeverity(IntEnum):
    ERROR = 1
    WARNING = 2
    INFORMATION = 3
    HINT = 4


class DiagnosticTag(IntEnum):
    UNNECESSARY = 1
    """ 
    Unused or unnecessary code
    """
    DEPRECATED = 2
    """
    Deprecated or obsolete code 
    """


class DiagnosticRelatedInformation(LspModel):
    location: Location
    """
    The location of this related diagnostic information.
    """
    message: str
    """
    The message of this related diagnostic information.
    """


class CodeDescription(LspModel):
    href: URI
    """
    URI to open with more info.
    """


class Diagnostic(LspModel):
    range: Range
    """
    The range at which the message applies.
    """
    severity: Optional[DiagnosticSeverity]
    """
    The diagnostic's severity.
    """
    code: Optional[Union[int, str]]
    """
    The diagnostic's code.
    """
    code_description: Optional[CodeDescription]
    """
    An URI to open with more information about the diagnostic error.
    """
    source: Optional[str]
    """
    A human-readable string describing the source of this diagnostic
    """
    message: str
    """
    The diagnostic's message.
    """
    tags: Optional[List[DiagnosticTag]]
    """
    Additional metadata about the diagnostic.
    """
    related_information: Optional[List[DiagnosticRelatedInformation]]
    """
    An array of related diagnostic information,
    e.g. when symbol-names within a scope collide all definitions can be marked via this property.
    """
    data: Optional[Any]
    """
    A data entry field that is preserved between
    a `textDocument/publishDiagnostics` notification and `textDocument/codeAction` request.
    """


class Command(LspModel):
    title: str
    """
    Title of the command, like `save`.
    """
    command: str
    """
    The identifier of the actual command handler.
    """
    arguments: Optional[List[Any]]
    """
    Arguments that the command handler should be invoked with.
    """


class TextEdit(LspModel):
    range: Range
    """
    The range of the text document to be manipulated.
    To insert text into a document create a range where start === end.
    """
    new_text: str
    """
    The text to be inserted. For delete operations use an empty string.
    """


class ChangeAnnotation(LspModel):
    label: str
    """
    A human-readable string describing the actual change.
    """
    needs_confirmation: Optional[bool]
    """
    A flag which indicates that user confirmation is needed before applying the change.
    """
    description: Optional[str]
    """
    A human-readable string which is rendered less prominent in the user interface.
    """


class AnnotatedTextEdit(TextEdit):
    annotation_id: ChangeAnnotationIdentifier
    """
    Thea actual annotation identifier.
    """


class TextDocumentIdentifier(LspModel):
    uri: DocumentUri
    """
    The text document's URI.
    """


class VersionedTextDocumentIdentifier(TextDocumentIdentifier):
    version: int
    """
    The version number of this document.
    The version number of a document will increase after each change,
    including undo/redo. The number doesn't need to be consecutive.
    """


class OptionalVersionedTextDocumentIdentifier(TextDocumentIdentifier):
    version: Optional[Union[int, None]]
    """
    The version number of this document. If an optional versioned text document
    identifier is sent from the server to the client and the file is not
    open in the editor (the server has not received an open notification
    before) the server can send `null` to indicate that the version is
    known and the content on disk is the master (as specified with document
    content ownership).
    The version number of a document will increase after each change,
    including undo/redo. The number doesn't need to be consecutive.
    """


class TextDocumentEdit(LspModel):
    text_document: OptionalVersionedTextDocumentIdentifier
    """
    The text document to change.
    """
    edits: List[Union[TextEdit, AnnotatedTextEdit]]
    """
    The edits to be applied.
    """


class CreateFileOptions(LspModel):
    """
    Options to create a file.
    """

    overwrite: Optional[bool]
    """
    Overwrite existing file. Overwrite wins over `ignoreIfExists`
    """
    ignore_if_exists: Optional[bool]
    """
    Ignore if exists.
    """


class CreateFile(LspModel):
    """
    Create file operation.
    """

    kind: str = "create"
    """
    A create.
    """
    uri: DocumentUri
    """
    The resource to create.
    """
    options: Optional[CreateFileOptions]
    """
    Additional options.
    """
    annotation_id: Optional[ChangeAnnotationIdentifier]
    """
    An optional annotation identifier describing the operation.
    """


class RenameFileOptions(LspModel):
    """
    Rename file options.
    """

    overwrite: Optional[bool]
    """
    Overwrite target if existing. Overwrite wins over `ignoreIfExists`.
    """
    ignore_if_exists: Optional[bool]
    """
    Ignores if target exists.
    """


class RenameFile(LspModel):
    """
    Rename file operation.
    """

    kind: str = "rename"
    """
    A rename.
    """
    old_uri: DocumentUri
    """
    The old (existing) location.
    """
    new_uri: DocumentUri
    """
    The new location.
    """
    options: Optional[RenameFileOptions]
    """
    Rename options.
    """
    annotation_id: Optional[ChangeAnnotationIdentifier]
    """
    An optional annotation identifier describing the operation.
    """


class DeleteFileOptions(LspModel):
    """
    Delete file options.
    """

    recursive: Optional[bool]
    """
    Delete the content recursively if a folder denoted.
    """
    ignore_if_not_exists: Optional[bool]
    """
    Ignore the operation if the file does not exists.
    """


class DeleteFile(LspModel):
    """
    Delete file operation
    """

    kind: str = "delete"
    """
    A delete.
    """
    uri: DocumentUri
    """
    The file to delete
    """
    options: Optional[RenameFileOptions]
    """
    Delete options.
    """
    annotation_id: Optional[ChangeAnnotationIdentifier]
    """
    An optional annotation identifier describing the operation.
    """


class WorkspaceEdit(LspModel):
    """
    :param changes: Holds changes to existing resources.

    :param document_changes: Depending on the client capability `workspace.workspaceEdit.resourceOperations`
        document changes are either an array of `TextDocumentEdit`s to express changes to n different text documents
        where each text document edit addresses a specific version of a text document.
        Or it can contain above `TextDocumentEdit`s mixed with create, rename and delete file / folder operations.

    :param change_annotations: A map of change annotations that can be referenced in `AnnotatedTextEdit`s or create,
        rename and delete file / folder operations.
    """

    # TODO


class ResourceOperationKind(Enum):
    CREATE = "create"
    RENAME = "rename"
    DELETE = "delete"


class FailureHandlingKind(Enum):
    ABORT = "abort"
    TRANSACTIONAL = "transactional"
    TEXT_ONLY_TRANSACTIONAL = "textOnlyTransactional"
    UNDO = "undo"


class ChangeAnnotationsSupport(LspModel):
    groups_on_label: Optional[bool]


class WorkspaceEditClientCapabilities(LspModel):
    document_changes: Optional[bool]
    """
    The client supports versioned document changes in `WorkspaceEdit`s
    """
    resource_operations: Optional[List[ResourceOperationKind]]
    """
    The resource operations the client supports.
    Clients should at least support 'create', 'rename' and 'delete' files and folders.
    """
    failure_handling: Optional[FailureHandlingKind]
    """
    The failure handling strategy of a client if applying the workspace edit fails.
    """
    normalizes_line_endings: Optional[bool]
    """
    Whether the client normalizes line endings to the client specific setting.
    If set to `true` the client will normalize line ending characters
    in a workspace edit to the client specific new line character(s).
    """
    # ?
    change_annotation_support: Optional[ChangeAnnotationsSupport]
    """
    Whether the client in general supports change annotations on text edits,
    create file, rename file and delete file changes.
    """


class TextDocumentItem(LspModel):
    uri: DocumentUri
    """
    The text document's URI.
    """
    language_id: str
    """
    The text document's language identifier.
    """
    version: int
    """
    The version number of this document (it will increase after each change, including undo/redo).
    """
    text: str
    """
    The content of the opened text document.
    """


class TextDocumentPositionParams(LspModel):
    text_document: TextDocumentIdentifier
    """
    The text document.
    """
    position: Position
    """
    The position inside the text document.z
    """


class DocumentFilter(LspModel):
    language: Optional[str] = None
    """
    A language ID, like 'typescript'.
    """
    scheme: Optional[str] = None
    """
     A Uri [scheme](#Uri.scheme), like `file` or `untitled`.
    """
    pattern: Optional[str] = None
    """
    Glob patterns can have the following syntax:
    * `*` to match one or more characters in a path segment
    * `?` to match on one character in a path segment
    * `**` to match any number of path segments, including none
    * `{}` to group sub patterns into an OR expression. (e.g. `**​/*.{ts,js}`
        matches all TypeScript and JavaScript files)
    * `[]` to declare a range of characters to match in a path segment
        (e.g., `example.[0-9]` to match on `example.0`, `example.1`, …)
    * `[!...]` to negate a range of characters to match in a path segment
        (e.g., `example.[!0-9]` to match on `example.a`, `example.b`, but
        not `example.0`)
    """


class StaticRegistrationOptions(LspModel):
    """
    Static registration options to be returned in the initialize request.
    """

    id: Optional[str] = None
    """
    The id used to register the request.
    The id can be used to deregister the request again. See also Registration#id.
    """


class TextDocumentRegistrationOptions(LspModel):
    """
    General text document registration options.
    """

    document_selector: Optional[List[DocumentFilter]] = None
    """
    A document selector to identify the scope of the registration.
    If set to null the document selector provided on the client side will be used.
    """


class MarkupKind(Enum):
    PLAIN_TEXT = "plaintext"
    MARKDOWN = "markdown"


class MarkupContent(LspModel):
    kind: MarkupKind
    """
    The type of the Markup.
    """
    value: str
    """
    The content itself.
    """


class MarkupClientCapabilities(LspModel):
    parser: MarkupKind
    """
    The name of the parser.
    """
    version: Optional[str]
    """
    The version of the parser.
    """
    allowed_tags: Optional[List[str]]
    """
    A list of HTML tags that the client allows / supports in Markdown.

    Known markdown parsers used by clients right now are:
    -------------------------------------------------------------
    Parser	            Version	    Documentation
    -------------------------------------------------------------
    marked	            1.1.0	    Marked Documentation
    Python-Markdown	    3.2.2	    Python-Markdown Documentation
    -------------------------------------------------------------
    """


class WorkDoneProgressBegin(LspModel):
    kind: str = "begin"
    title: str
    """
    Mandatory title of the progress operation. Used to briefly inform about
    the kind of operation being performed.

    Examples: "Indexing" or "Linking dependencies".
    """
    cancellable: Optional[bool]
    """
    Controls if a cancel button should show to allow the user to cancel the
    long running operation. Clients that don't support cancellation are
    allowed to ignore the setting.
    """
    message: Optional[str]
    """
    Optional, more detailed associated progress message. Contains
    complementary information to the `title`.

    Examples: "3/25 files", "project/src/module2", "node_modules/some_dep".
    If unset, the previous progress message (if any) is still valid.
    """
    percentage: Optional[int]  # uint8
    """
    Optional progress percentage to display (value 100 is considered 100%).
    If not provided infinite progress is assumed and clients are allowed
    to ignore the `percentage` value in subsequent in report notifications.
    """


class WorkDoneProgressReport(LspModel):
    kind: str = "report"
    cancellable: Optional[bool]
    """
    Controls if a cancel button should show to allow the user to cancel the
    long running operation. Clients that don't support cancellation are
    allowed to ignore the setting.
    """
    message: Optional[str]
    """
    Optional, more detailed associated progress message. Contains
    complementary information to the `title`.
    """
    percentage: Optional[int]  # uint8
    """
    Optional progress percentage to display (value 100 is considered 100%).
    If not provided infinite progress is assumed and clients are allowed
    to ignore the `percentage` value in subsequent in report notifications.
    """


class WorkDoneProgressEnd(LspModel):
    kind: str = "end"
    message: Optional[bool]
    """
    Optional, a final message indicating to for example indicate the outcome
    of the operation.
    """


class WorkDoneProgressParams(LspModel):
    work_done_token: Optional[ProgressToken]
    """
    An optional token that a server can use to report work done progress.
    """


class WorkDoneProgressOptions(LspModel):
    work_done_progress: Optional[bool] = None


class PartialResultParams(LspModel):
    partial_result_token: Optional[ProgressToken]
    """
    An optional token that a server can use to report partial results (e.g.streaming)
    to the client.
    """


# ##################### Lifecycle Message #####################


class ClientCapabilitiesWorkspaceFileOperation(LspModel):
    dynamic_registration: Optional[bool]
    did_create: Optional[bool]
    will_create: Optional[bool]
    did_rename: Optional[bool]
    will_rename: Optional[bool]
    did_delete: Optional[bool]
    will_delete: Optional[bool]


class InitializeErrorCodes(IntEnum):
    unknown_protocol_version = 1


class InitializeError(LspModel):
    retry: bool


class InitializedParams(LspModel):
    pass


class MessageType(IntEnum):
    ERROR = 1
    WARNING = 2
    INFO = 3
    LOG = 4


class ShowMessageParams(LspModel):
    type: MessageType
    message: str


class ShowMessageRequestClientCapabilitiesMessageActionItem(LspModel):
    additional_properties_support: Optional[bool]


class ShowMessageRequestClientCapabilities(LspModel):
    message_action_item: Optional[ShowMessageRequestClientCapabilitiesMessageActionItem]


class MessageActionItem(LspModel):
    title: str


class ShowMessageRequestParams(LspModel):
    type: MessageType
    message: str
    actions: Optional[List[MessageActionItem]]


class ShowDocumentClientCapabilities(LspModel):
    support: bool


class ShowDocumentParams(LspModel):
    uri: URI
    external: Optional[bool]
    take_focus: Optional[bool]
    selection: Optional[Range]


class ShowDocumentResult(LspModel):
    success: bool
    """
    A boolean indicating if the show was successful.
    """


class LogMessageParams(LspModel):
    type: MessageType
    """
    The message type
    """
    message: str
    """
    The actual message
    """


class PublishDiagnosticsParams(LspModel):
    uri: DocumentUri
    """
    The URI for which diagnostic information is reported.
    """
    version: Optional[int]
    """
    Optional the version number of the document the diagnostics are published for.

    @since 3.15.0
    """
    diagnostics: List[Diagnostic]
    """
    An array of diagnostic information items.
    """


class WorkDoneProgressCreateParams(LspModel):
    token: ProgressToken
    """
    The token to be used to report progress.
    """


class WorkDoneProgressCancelParams(LspModel):
    token: ProgressToken


class Registration(LspModel):
    id: str
    """
    The id used to register the request. The id can be used to deregister
    the request again.
    """
    method: str
    """
    The method / capability to register for.
    """
    registration_options: Optional[Any]
    """
    Options necessary for the registration.
    """


class RegistrationParams(LspModel):
    registrations: List[Registration]


class Unregistration(LspModel):
    id: str
    """
    The id used to unregister the request or notification. Usually an id
    provided during the register request.
    """
    method: str
    """
    The method / capability to unregister for.
    """


class UnregistrationParams(LspModel):
    unregistrations: List[Unregistration]


class SetTraceParams(LspModel):
    value: TraceValue
    """
    The new value that should be assigned to the trace setting.
    """


class LogTraceParams(LspModel):
    message: str
    """
    The message to be logged.
    """
    verbose: Optional[str]
    """
    Additional information that can be computed if the `trace` configuration
    is set to `'verbose'`
    """


class SymbolKind(IntEnum):
    FILE = 1
    MODULE = 2
    NAMESPACE = 3
    PACKAGE = 4
    CLASS = 5
    METHOD = 6
    PROPERTY = 7
    FIELD = 8
    CONSTRUCTOR = 9
    ENUM = 10
    INTERFACE = 11
    FUNCTION = 12
    VARIABLE = 13
    CONSTANT = 14
    STRING = 15
    NUMBER = 16
    BOOLEAN = 17
    ARRAY = 18
    OBJECT = 19
    KEY = 20
    NULL = 21
    ENUMMEMBER = 22
    STRUCT = 23
    EVENT = 24
    OPERATOR = 25
    TYPEPARAMETER = 26


class SymbolTag(IntEnum):
    DEPRECATED = 1


class DocumentSymbol(LspModel):
    name: str
    detail: Optional[str]
    kind: SymbolKind
    tags: Optional[List[SymbolTag]]
    deprecated: Optional[bool]
    range: Range
    selection_range: Range
    children: Optional[List["DocumentSymbol"]]


class SymbolInformation(LspModel):
    name: str
    kind: SymbolKind
    tags: Optional[List[SymbolTag]]
    deprecated: Optional[bool]
    location: Location
    container_name: Optional[str]


class WorkspaceSymbolClientCapabilitiesSymbolKind(LspModel):
    value_set: Optional[List[SymbolKind]]


class WorkspaceSymbolClientCapabilitiesTagSupport(LspModel):
    value_set: List[SymbolTag]


class WorkspaceSymbolClientCapabilitiesResolveSupport(LspModel):
    properties: List[str]


class WorkspaceSymbolClientCapabilities(LspModel):
    dynamic_registration: Optional[bool]
    symbol_kind: Optional[WorkspaceSymbolClientCapabilitiesSymbolKind]
    tag_support: Optional[WorkspaceSymbolClientCapabilitiesTagSupport]
    resolve_support: Optional[WorkspaceSymbolClientCapabilitiesResolveSupport]


class WorkspaceSymbolOptions(WorkDoneProgressOptions):
    resolve_provider: Optional[bool]


class WorkspaceSymbolRegistrationOptions(WorkspaceSymbolOptions):
    pass


class WorkspaceSymbolParams(WorkDoneProgressParams, PartialResultParams):
    query: str


class WorkspaceSymbol(LspModel):
    name: str
    kind: SymbolKind
    tags: Optional[List[SymbolTag]]
    location: Union[Location, DocumentUri]
    container_name: Optional[str]


class ConfigurationItems(LspModel):
    scope_uri: Optional[DocumentUri]
    section: Optional[bool]


class ConfigurationParams(LspModel):
    items: Optional[List[ConfigurationItems]]


class DidChangeConfigurationClientCapabilities(LspModel):
    dynamic_registration: Optional[bool]


class DidChangeConfigurationParams(LspModel):
    settings: Any


class WorkspaceFolder(LspModel):
    uri: DocumentUri
    name: str


class WorkspaceFoldersChangeEvent(LspModel):
    added: List[WorkspaceFolder]
    removed: List[WorkspaceFolder]


class DidChangeWorkspaceFoldersParams(LspModel):
    event: WorkspaceFoldersChangeEvent


class FileCreate(LspModel):
    uri: str


class CreateFilesParams(LspModel):
    files: List[FileCreate]


class FileRename(LspModel):
    old_uri: str
    new_uri: str


class RenameFilesParams(LspModel):
    files: List[FileRename]


class FileDelete(LspModel):
    uri: str


class DeleteFilesParams(LspModel):
    files: List[FileDelete]


class DidChangeWatchedFilesClientCapabilities(LspModel):
    dynamic_registration: Optional[bool]


class FileSystemWatcher(LspModel):
    glob_pattern: str
    kind: Optional[int]  # uint


class DidChangeWatchedFilesRegistrationOptions(LspModel):
    watchers: List[FileSystemWatcher]


class WatchKind(IntEnum):
    CREATE = 1
    CHANGE = 2
    DELETE = 4


class FileEvent(LspModel):
    uri: DocumentUri
    type: int  # uint


class DidChangeWatchedParams(LspModel):
    changes: List[FileEvent]


class FileChangeType(IntEnum):
    CREATED = 1
    CHANGED = 1
    DELETED = 3


class ExecuteCommandClientCapabilities(LspModel):
    dynamic_registration: Optional[bool]


class ExecuteCommandOptions(WorkDoneProgressOptions):
    commands: List[str]


class ExecuteCommandRegistrationOptions(ExecuteCommandOptions):
    pass


class ExecuteCommandParams(WorkDoneProgressParams):
    command: str
    arguments: Optional[List[Any]]


class ApplyWorkspaceEditParams(LspModel):
    label: Optional[str]
    edit: WorkspaceEdit


class ApplyWorkspaceEditResult(LspModel):
    applied: bool
    failure_reason: Optional[str]
    failed_change: Optional[int]  # uint


class CodeLensWorkspaceClientCapabilities(LspModel):
    refresh_support: Optional[bool]


class SemanticTokensClientCapabilitiesRequestsFull(LspModel):
    delta: Optional[bool]


class SemanticTokensClientCapabilitiesRequests(LspModel):
    range: Optional[bool]
    full: Optional[Union[bool, SemanticTokensClientCapabilitiesRequestsFull]]


class TokenFormat(LspModel):
    pass


class SemanticTokensClientCapabilities(LspModel):
    dynamic_registration: Optional[bool]
    requests: Optional[SemanticTokensClientCapabilitiesRequests]
    token_types: List[str] = []
    token_modifiers: List[str] = []
    formats: List[TokenFormat] = []
    overlapping_token_support: Optional[bool]
    multiline_token_support: Optional[bool]
    server_cancel_support: Optional[bool]
    augments_syntax_tokens: Optional[bool]


class SemanticTokensWorkspaceClientCapabilities(LspModel):
    refresh_support: Optional[bool]


class TextDocumentSyncClientCapabilities(LspModel):
    dynamic_registration: Optional[bool]
    will_save: Optional[bool]
    will_save_wait_until: Optional[bool]
    did_save: Optional[bool]


class ClientCapabilitiesWorkspace(LspModel):
    apply_edit: Optional[bool]
    workspace_edit: Optional[WorkspaceEditClientCapabilities]
    did_change_configuration: Optional[DidChangeConfigurationClientCapabilities]
    did_change_watched_files: Optional[DidChangeWatchedFilesClientCapabilities]
    symbol: Optional[WorkspaceSymbolClientCapabilities]
    execute_command: Optional[ExecuteCommandClientCapabilities]
    workspace_folders: Optional[bool]
    configuration: Optional[bool]
    semantic_tokens: Optional[SemanticTokensWorkspaceClientCapabilities]
    code_lens: Optional[CodeLensWorkspaceClientCapabilities]
    file_operations: Optional[ClientCapabilitiesWorkspaceFileOperation]


class TextDocumentClientCapabilities(LspModel):
    synchronization: Optional[TextDocumentSyncClientCapabilities]
    """
    completion: Optional[CompletionClientCapabilities]
    hover: Optional[HoverClientCapabilities]
    signature_help: Optional[SignatureHelpClientCapabilities]
    declaration: Optional[DeclarationClientCapabilities]
    definition: Optional[DefinitionClientCapabilities]
    type_definition: Optional[TypeDefinitionClientCapabilities]
    implementation: Optional[ImplementationClientCapabilities]
    references: Optional[ReferenceClientCapabilities]
    document_highlight: Optional[DocumentHighlightClientCapabilities]
    document_symbol: Optional[DocumentSymbolClientCapabilities]
    code_action: Optional[CodeActionClientCapabilities]
    document_link: Optional[DocumentLinkClientCapabilities]
    color_provider: Optional[DocumentColorClientCapabilities]
    formatting: Optional[DocumentFormattingClientCapabilities]
    range_formatting: Optional[DocumentRangeFormattingClientCapabilities]
    on_type_formatting: Optional[DocumentOnTypeFormattingClientCapabilities]
    rename: Optional[RenameClientCapabilities]
    publish_diagnostic: Optional[PublishDiagnosticsClientCapabilities]
    folding_range: Optional[FoldingRangeClientCapabilities]
    selection_range: Optional[SelectionRangeClientCapabilities]
    linked_editing_range: Optional[LinkedEditingRangeClientCapabilities]
    call_hierarchy: Optional[CallHierarchyClientCapabilities]
    semantic_tokens: Optional[SemanticTokensClientCapabilities]
    moniker: Optional[MonikerClientCapabilities]
    type_hierarchy: Optional[TypeHierarchyClientCapabilities]
    inline_valie: Optional[InlineValueClientCapabilities]
    inlay_hint: Optional[InlayHintClientCapabilities]
    """


class ClientCapabilitiesGeneralStaleRequestSupport(LspModel):
    cancel: bool
    retry_on_content_modified: List[str]


class ClientCapabilitiesGeneral(LspModel):
    stale_request_support: Optional[ClientCapabilitiesGeneralStaleRequestSupport]
    regular_expressions: Optional[RegularExpressionsClientCapabilities]
    """
    markdown: Optional[MarkdownClientCapabilities]
    """


class ClientCapabilitiesWindow(LspModel):
    work_done_progress: Optional[bool]
    show_message: Optional[ShowMessageRequestClientCapabilities]
    show_document: Optional[ShowDocumentClientCapabilities]


class NotebookDocumentSyncClientCapabilities(LspModel):
    dynamic_registration: Optional[bool]
    execution_summary_support: Optional[bool]


class NotebookDocumentClientCapabilities(LspModel):
    synchronization: NotebookDocumentSyncClientCapabilities


class ClientCapabilities(LspModel):
    workspace: Optional[ClientCapabilitiesWorkspace]
    text_document: Optional[TextDocumentClientCapabilities]
    notebook_document: Optional[NotebookDocumentClientCapabilities]
    window: Optional[ClientCapabilitiesWindow]
    general: Optional[ClientCapabilitiesGeneral]
    experimental: Optional[Any]


class InitializeParamsClientInfo(LspModel):
    name: str
    version: Optional[str]


class InitializeParams(LspModel):
    process_id: Optional[int]
    client_info: Optional[InitializeParamsClientInfo]
    locale: Optional[str]
    root_path: Optional[str]
    root_uri: Optional[DocumentUri]
    initialization_options: Optional[Any]
    capabilities: ClientCapabilities
    trace: Optional[TraceValue]
    workspace_folders: Optional[List[WorkspaceFolder]]
