from enum import Enum
from typing import Any, List, Optional, Union

from woke.lsp.common_structures import WorkspaceSymbolOptions
from woke.lsp.document_sync import TextDocumentSyncKind, TextDocumentSyncOptions

from .features.document_link import DocumentLinkOptions
from .lsp_data_model import LspModel


class PositionEncodingKind(str, Enum):
    UTF8 = "utf-8"
    UTF16 = "utf-16"
    UTF32 = "utf-32"


class WorkspaceFoldersServerCapabilities(LspModel):
    supported: Optional[bool]
    change_notifications: Optional[Union[str, bool]]


class FileOperationPatternKind(Enum):
    FILE = "file"
    FOLDER = "folder"


class FileOperationPatternOptions(LspModel):
    ignore_case: Optional[bool]


class FileOperationPattern(LspModel):
    glob: str
    matches: Optional[FileOperationPatternKind]
    options: Optional[FileOperationPatternOptions]


class FileOperationFilter(LspModel):
    scheme: Optional[str]
    pattern: FileOperationPattern


class FileOperationRegistrationOptions(LspModel):
    filters: List[FileOperationFilter]


class ServerCapabilitiesWorkspaceFileOperations(LspModel):
    """
    ServerCapabilities subsubClass
    """

    did_create: Optional[FileOperationRegistrationOptions]
    will_create: Optional[FileOperationRegistrationOptions]
    did_rename: Optional[FileOperationRegistrationOptions]
    will_rename: Optional[FileOperationRegistrationOptions]
    did_delete: Optional[FileOperationRegistrationOptions]
    will_delete: Optional[FileOperationRegistrationOptions]


class ServerCapabilitiesWorkspace(LspModel):
    """
    ServerCapabilities subClass
    """

    workspace_folders: Optional[WorkspaceFoldersServerCapabilities]
    file_operations: Optional[ServerCapabilitiesWorkspaceFileOperations]


class ServerCapabilities(LspModel):
    position_encoding: Optional[PositionEncodingKind] = None
    text_document_sync: Optional[
        Union[TextDocumentSyncOptions, TextDocumentSyncKind]
    ] = None
    document_link_provider: Optional[DocumentLinkOptions] = None
    """
    completion_provider: Optional[CompletionOptions]
    hover_provider: Optional[Union[bool, HoverOptions]]
    signature_help_provider: Optional[SignatureHelpOptions]
    declaration_provider: Optional[Union[bool, DeclarationOptions, DeclarationRegistrationOptions]]
    definition_provider: Optional[Union[bool, DefinitionOptions]]
    type_definition_provider: Optional[Union[bool, TypeDefinitionOptions, TypeDefinitionRegistrationOptions]]
    implementation_provider: Optional[Union[bool, ImplementationOptions, ImplementationRegistrationOptions]]
    references_provider: Optional[Union[bool, ReferenceOptions]]
    document_highlight_provider: Optional[Union[bool, ReferenceOptions]]
    document_symbol_provider: Optional[Union[bool, DocumentSymbolOptions]]
    code_action_provider: Optional[Union[bool, CodeActionOptions]]
    code_lens_provider: Optional[CodeLensOptions]
    color_provider: Optional[Union[bool, DocumentColorOptions, DocumentColorRegistrationOptions]]
    document_formatting_provider: Optional[Union[bool, DocumentFormattingOptions]]
    document_range_formatting_provider: Optional[Union[bool, DocumentRangeFormattingOptions]]
    document_on_type_formatting_provider: Optional[DocumentOnTypeFormattingOptions]
    rename_provider: Optional[Union[bool, RenameOptions]]
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
