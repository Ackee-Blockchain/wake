from pydantic import BaseModel
import enum
from typing import Any, List, Optional, Union, NewType, Array

DocumentUri = NewType["URI", str]
URI = NewType["URI", str]
ChangeAnnotationIdentifier = NewType["ChangeAnnotationIdentifier", str]
ProgressToken = Union[int, str]


class RegularExpressionsClientCapabilities(BaseModel):
    engine: str
    """
    The engine's name.
    """
    version: Optional[str]
    """
    The engine's version.
    """


class Position(BaseModel):
    line: int
    """
    Position in a document (zero-based).
    """
    character: int
    """
    Character offset on a line in a document (zero-based).between the `character` and `character + 1`.
    """


class Range(BaseModel):
    start: Position
    """
    The range's start position.
    """
    end: Position
    """
    The range's end position.
    """


class Location(BaseModel):
    """
    Represents a location inside a resource, such as a line inside a text file.
    """
    uri: DocumentUri
    range: Range


class LocationLink(BaseModel):
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


class DiagnosticSeverity(enum.IntEnum):
    ERROR = 1
    WARNING = 2
    INFORMATION = 3
    HINT = 4


class DiagnosticTag(enum):
    UNNECESSARY = 1
    """ 
    Unused or unnecessary code
    """ 
    DEPRECATED = 2
    """
    Deprecated or obsolete code 
    """

class DiagnosticRelatedInformation(BaseModel):
    location: Location
    """
    The location of this related diagnostic information.
    """
    message: str
    """
    The message of this related diagnostic information.
    """


class CodeDescription(BaseModel):
    href: URI
    """
    URI to open with more info.
    """


class Diagnostic(BaseModel):
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


class Command(BaseModel):
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


class TextEdit(BaseModel):
    range: Range
    """
    The range of the text document to be manipulated.
    To insert text into a document create a range where start === end.
    """
    new_text: str
    """
    The text to be inserted. For delete operations use an empty string.
    """

class ChangeAnnotation(BaseModel):
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


class TextDocumentIdentifier(BaseModel):
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


class TextDocumentEdit(BaseModel):
    text_document: OptionalVersionedTextDocumentIdentifier
    """
    The text document to change.
    """
    edits: List[Union[TextEdit, AnnotatedTextEdit]]
    """
    The edits to be applied.
    """


class CreateFileOptions(BaseModel):
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


class CreateFile(BaseModel):
    """
    Create file operation.
    """
    kind: str = 'create'
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


class RenameFileOptions(BaseModel):
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


class RenameFile(BaseModel):
    """
    Rename file operation.
    """
    kind: str = 'rename'
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


class DeleteFileOptions(BaseModel):
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




class DeleteFile(BaseModel):
    """
    Delete file operation
    """
    kind: str = 'delete'
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

class WorkspaceEdit(BaseModel):
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


class ResourceOperationKind(enum.StrEnum):
    CREATE = 'create'
    RENAME = 'rename'
    DELETE = 'delete'


class FailureHandlingKind(enum.StrEnum):
    ABORT = 'abort'
    TRANSACTIONAL = 'transactional'
    TEXT_ONLY_TRANSACTIONAL = 'textonlytransactional'
    UNDO = 'undo'


class WorkspaceEditClientCapabilities(BaseModel):
    document_changes: Optional[bool]
    """
    The client supports versioned document changes in `WorkspaceEdit`s
    """
    resource_operations: Optional[List[ResourceOperationKind]]
    """
    The resource operations the client supports.
    Clients should at least support 'create', 'rename' and 'delete' files and folders.
    """
    failure_handlings: Optional[FailureHandlingKind]
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
    change_annotation_support: Optional[bool] 
    """
    Whether the client in general supports change annotations on text edits,
    create file, rename file and delete file changes.
    """



class TextDocumentItem(BaseModel):
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


class TextDocumentPositionParams(BaseModel):
    text_document: TextDocumentIdentifier
    """
    The text document.
    """
    position: Position
    """
    The position inside the text document.z
    """


class DocumentFilter(BaseModel):
    language: Optional[str]
    """
    A language ID, like 'typescript'.
    """
    scheme: Optional[str]
    """
     A Uri [scheme](#Uri.scheme), like `file` or `untitled`.
    """
    pattern: Optional[str]
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


class StaticRegistrationOptions(BaseModel):
    """
    Static registration options to be returned in the initialize request.
    """
    id: Optional[str]
    """
    The id used to register the request.
    The id can be used to deregister the request again. See also Registration#id.
    """


class TextDocumentRegistrationOptions(BaseModel):
    """
    General text document registration options.
    """
    document_selector: Union[List[DocumentFilter], None]
    """
    A document selector to identify the scope of the registration.
    If set to null the document selector provided on the client side will be used.
    """


class MarkupKind(enum.StrEnum):
    PLAIN_TEXT = "plaintext"
    MARKDOWN = "markdown"


class MarkupContent(BaseModel):
    kind: MarkupKind
    """
    The type of the Markup.
    """
    value: str
    """
    The content itself.
    """


class MarkupClientCapabilities(BaseModel):
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


class WorkDoneProgressBegin(BaseModel):
    kind: str  = "begin"
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
    percentage: Optional[uint8]
    """
    Optional progress percentage to display (value 100 is considered 100%).
	If not provided infinite progress is assumed and clients are allowed
	to ignore the `percentage` value in subsequent in report notifications.
    """


class  WorkDoneProgressReport(BaseModel):
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
    percentage: Optional[uint8]
    """
    Optional progress percentage to display (value 100 is considered 100%).
	If not provided infinite progress is assumed and clients are allowed
	to ignore the `percentage` value in subsequent in report notifications.
    """


class WorkDoneProgressEnd(BaseModel):
    kind: str = "end"
    message: Optional[bool]
    """
    Optional, a final message indicating to for example indicate the outcome
	of the operation.
    """


class WorkDoneProgressParams(BaseModel):
    work_done_token: Optional[ProgressToken]
    """
    An optional token that a server can use to report work done progress.
    """


class WorkDoneProgressOptions(BaseModel):
    work_done_progress: Optional[bool]


class PartialResultParams(BaseModel):
    partial_result_token: Optional[ProgressToken]
    """
    An optional token that a server can use to report partial results (e.g.streaming)
    to the client.
    """

