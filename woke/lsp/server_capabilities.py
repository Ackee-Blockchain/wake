from enum import Enum
from typing import Any, List, Optional, Union

from woke.lsp.common_structures import WorkspaceSymbolOptions
from woke.lsp.document_sync import TextDocumentSyncKind, TextDocumentSyncOptions

from .features.code_lens import CodeLensOptions
from .features.definition import DefinitionOptions
from .features.document_link import DocumentLinkOptions
from .features.document_symbol import DocumentSymbolOptions
from .features.implementation import (
    ImplementationOptions,
    ImplementationRegistrationOptions,
)
from .features.references import ReferenceOptions
from .features.rename import RenameOptions
from .features.type_definition import (
    TypeDefinitionOptions,
    TypeDefinitionRegistrationOptions,
)
from .features.type_hierarchy import (
    TypeHierarchyOptions,
    TypeHierarchyRegistrationOptions,
)
from .lsp_data_model import LspModel


class PositionEncodingKind(str, Enum):
    UTF8 = "utf-8"
    UTF16 = "utf-16"
    UTF32 = "utf-32"


class WorkspaceFoldersServerCapabilities(LspModel):
    supported: Optional[bool] = None
    change_notifications: Optional[Union[str, bool]] = None


class FileOperationPatternKind(Enum):
    FILE = "file"
    FOLDER = "folder"


class FileOperationPatternOptions(LspModel):
    ignore_case: Optional[bool]


class FileOperationPattern(LspModel):
    glob: str
    """
    The glob pattern to match. Glob patterns can have the following syntax:
    - `*` to match one or more characters in a path segment
    - `?` to match one character in a path segment
    - `**` to match one or more characters in a path segment, including none
    - `{}` to group sub patterns into an OR expression. (e.g. `**/*.{ts,js}`
        matches all TypeScript and JavaScript files)
    - `[]` to declare a range of characters to match in a path segment
        (e.g., `example.[0-9]` to match `example.0`, `example.1`, …)
    - `[!...]` to negate a range of characters to match in a path segment
        (e.g., `example.[!0-9]` to match `example.a`, `example.b`, but
        not `example.0`)
    """
    matches: Optional[FileOperationPatternKind] = None
    """
    Whether to match files or folders with this pattern.

    Matches both if undefined.
    """
    options: Optional[FileOperationPatternOptions] = None
    """
    Additional options used during matching.
    """


class FileOperationFilter(LspModel):
    scheme: Optional[str] = None
    """
    A Uri like `file` or `untitled`.
    """
    pattern: FileOperationPattern
    """
    The actual file operation pattern.
    """


class FileOperationRegistrationOptions(LspModel):
    filters: List[FileOperationFilter]
    """
    The actual filters.
    """


class ServerCapabilitiesWorkspaceFileOperations(LspModel):
    """
    ServerCapabilities subsubClass
    """

    did_create: Optional[FileOperationRegistrationOptions] = None
    will_create: Optional[FileOperationRegistrationOptions] = None
    did_rename: Optional[FileOperationRegistrationOptions] = None
    will_rename: Optional[FileOperationRegistrationOptions] = None
    did_delete: Optional[FileOperationRegistrationOptions] = None
    will_delete: Optional[FileOperationRegistrationOptions] = None


class ServerCapabilitiesWorkspace(LspModel):
    """
    ServerCapabilities subClass
    """

    workspace_folders: Optional[WorkspaceFoldersServerCapabilities] = None
    file_operations: Optional[ServerCapabilitiesWorkspaceFileOperations] = None


class ServerCapabilities(LspModel):
    position_encoding: Optional[PositionEncodingKind] = None
    text_document_sync: Optional[
        Union[TextDocumentSyncOptions, TextDocumentSyncKind]
    ] = None
    document_link_provider: Optional[DocumentLinkOptions] = None
    type_hierarchy_provider: Optional[
        Union[bool, TypeHierarchyOptions, TypeHierarchyRegistrationOptions]
    ] = None
    references_provider: Optional[Union[bool, ReferenceOptions]] = None
    document_symbol_provider: Optional[Union[bool, DocumentSymbolOptions]] = None
    definition_provider: Optional[Union[bool, DefinitionOptions]] = None
    implementation_provider: Optional[
        Union[bool, ImplementationOptions, ImplementationRegistrationOptions]
    ] = None
    type_definition_provider: Optional[
        Union[bool, TypeDefinitionOptions, TypeDefinitionRegistrationOptions]
    ] = None
    code_lens_provider: Optional[CodeLensOptions] = None
    rename_provider: Optional[Union[bool, RenameOptions]] = None
    """
    completion_provider: Optional[CompletionOptions]
    hover_provider: Optional[Union[bool, HoverOptions]]
    signature_help_provider: Optional[SignatureHelpOptions]
    declaration_provider: Optional[Union[bool, DeclarationOptions, DeclarationRegistrationOptions]]
    document_highlight_provider: Optional[Union[bool, ReferenceOptions]]
    code_action_provider: Optional[Union[bool, CodeActionOptions]]
    color_provider: Optional[Union[bool, DocumentColorOptions, DocumentColorRegistrationOptions]]
    document_formatting_provider: Optional[Union[bool, DocumentFormattingOptions]]
    document_range_formatting_provider: Optional[Union[bool, DocumentRangeFormattingOptions]]
    document_on_type_formatting_provider: Optional[DocumentOnTypeFormattingOptions]
    folding_range_provider: Optional[Union[bool, FoldingRangeOptions, FoldingRangeRegistrationOptions]]
    execute_command_rovider: Optional[ExecuteCommandOptions]
    selection_range_provider: Optional[Union[bool, SelectionRangeOptions, SelectionRangeRegistrationOptions]]
    linked_editing_range_provider: Optional[Union[bool, LinkedEditingRangeOptions, LinkedEditingRangeRegistrationOptions]]
    call_hierarchy_provider: Optional[Union[bool, CallHierarchyOptions, CallHierarchyRegistrationOptions]]
    semantic_token_provider: Optional[Union[SemanticTokensOptions, SemanticTokensRegistrationOptions]]
    moniker_provider: Optional[Union[bool, MonikerOptions, MonikerRegistrationOptions]]
    diagnostic_provider: Optional[
        Union[DiagnosticOptions, DiagnosticRegistrationOptions]
    ] = None
    """
    workspace_symbol_provider: Optional[Union[bool, WorkspaceSymbolOptions]] = None
    workspace: Optional[ServerCapabilitiesWorkspace] = None
    experimental: Optional[Any] = None


class InitializeResultServerInfo(LspModel):
    name: str
    version: Optional[str]


class InitializeResult(LspModel):
    capabilities: ServerCapabilities
    server_info: Optional[InitializeResultServerInfo]
