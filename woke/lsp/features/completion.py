import enum
from typing import Any, List, Optional, Union

from ..common_structures import (
    Command,
    MarkupContent,
    MarkupKind,
    PartialResultParams,
    Range,
    TextDocumentPositionParams,
    TextDocumentRegistrationOptions,
    TextEdit,
    WorkDoneProgressOptions,
    WorkDoneProgressParams,
)
from ..lsp_data_model import LspModel


class CompletionItemKind(enum.IntEnum):
    Text = 1
    Method = 2
    Function = 3
    Constructor = 4
    Field = 5
    Variable = 6
    Class = 7
    Interface = 8
    Module = 9
    Property = 10
    Unit = 11
    Value = 12
    Enum = 13
    Keyword = 14
    Snippet = 15
    Color = 16
    File = 17
    Reference = 18
    Folder = 19
    EnumMember = 20
    Constant = 21
    Struct = 22
    Event = 23
    Operator = 24
    TypeParameter = 25


class CompletionItemTag(enum.IntEnum):
    const = 1
    """
    Render a completion as obsolete, usually using a strike-out.
    """


class InsertTextMode(enum.IntEnum):
    as_is = 1
    """
    The insertion or replace strings is taken as it is. If the
    value is multi line the lines below the cursor will be
    inserted using the indentation defined in the string value.
    The client will not apply any kind of adjustments to the
    string.
    """
    adjust_Indentation = 2
    """
    The editor adjusts leading whitespace of new lines so that
    they match the indentation up to the cursor of the line for
    which the item is accepted.
    """


class InsertTextFormat(enum.IntEnum):
    plain_text = 1
    """
    The primary text to be inserted is treated as a plain string.
    """
    snippet = 2
    """
    The primary text to be inserted is treated as a snippet.
    A snippet can define tab stops and placeholders with `$1`, `$2`
    and `${3:foo}`. `$0` defines the final tab stop, it defaults to
    the end of the snippet. Placeholders with equal identifiers are linked,
    that is typing in one will update others too.
    """


#################################################################
# ########## ClientCapabilitiesCompletionItem subclasses ########


class ClientCapabilitiesCompletionItemTagSupport(LspModel):
    value_set: List[CompletionItemTag]


class ClientCapabilitiesCompletionItemResolveSupport(LspModel):
    properties: List[str]
    """
    The properties that a client can resolve lazily.
    """


class ClientCapabilitiesCompletionItemKind(LspModel):
    value_set: Optional[CompletionItemKind]
    """
    If this property is not present the client only supports
    the completion items kinds from `Text` to `Reference` as defined in
    the initial version of the protocol.
    """


#################################################################
# ########## CompletionClientCapabilities subclasses ############


class ClientCapabilitiesCompletionItem(LspModel):
    snippet_support: Optional[bool]
    """
    Client supports snippets as insert text.
    A snippet can define tab stops and placeholders with `$1`, `$2`
    and `${3:foo}`. `$0` defines the final tab stop, it defaults to
    the end of the snippet. Placeholders with equal identifiers are
    linked, that is typing in one will update others too.
    """
    commit_characters_support: Optional[bool]
    """
    Client supports commit characters on a completion item.
    """
    documentation_format: Optional[MarkupKind]
    """
    Client supports the following content formats for the documentation
    property. The order describes the preferred format of the client.
    """
    deprecated_support: Optional[bool]
    """
    Client supports the deprecated property on a completion item.
    """
    preselect_support: Optional[bool]
    """
    Client supports the preselect property on a completion item.
    """
    tag_support: Optional[ClientCapabilitiesCompletionItemTagSupport]
    """
    Client supports the tag property on a completion item. Clients
    supporting tags have to handle unknown tags gracefully. Clients
    especially need to preserve unknown tags when sending a completion
    item back to the server in a resolve call.
    """
    insert_replace_support: Optional[bool]
    """
    Client supports insert replace edit to control different behavior if
    a completion item is inserted in the text or should replace text.
    """
    resolve_support: Optional[ClientCapabilitiesCompletionItemResolveSupport]
    """
    Indicates which properties a client can resolve lazily on a
    completion item. Before version 3.16.0 only the predefined properties
    `documentation` and `detail` could be resolved lazily.
    """
    insert_text_mode_support: Optional[List[InsertTextMode]]
    """
    The client supports the `insertTextMode` property on
    a completion item to override the whitespace handling mode
    as defined by the client (see `insertTextMode`).
    """
    label_details_support: Optional[bool]


class ClientCapabilitiesCompletionList(LspModel):
    item_defaults: Optional[List[str]]
    """
    The value lists the supported property names of the
    `CompletionList.itemDefaults` object. If omitted
    no properties are supported.
    """


#################################################################


class CompletionClientCapabilities(LspModel):
    dynamic_registration: Optional[bool]
    """
    Whether completion supports dynamic registration.
    """
    completion_item: Optional[ClientCapabilitiesCompletionItem]
    """
    The client supports the following `CompletionItem` specific
    capabilities.
    """
    completion_item_kind: Optional[ClientCapabilitiesCompletionItemKind]
    """
    The completion item kind values the client supports. When this
    property exists the client also guarantees that it will
    handle values outside its set gracefully and falls back
    to a default value when unknown.
    """
    context_support: Optional[bool]
    """
    The client supports to send additional context information for a
    `textDocument/completion` request.
    """
    insert_text_mode: Optional[InsertTextMode]
    """
    The client's default when the completion item doesn't provide a
    `insertTextMode` property.
    """
    completion_list: Optional[ClientCapabilitiesCompletionList]
    """
    The client supports the following `CompletionList` specific
    capabilities.
    """


#################################################################
# ########## CompletionOptions subclass #########################


class OptionsCompletionItem(LspModel):
    label_details_support: Optional[bool]
    """
    The server has support for completion item label
    details (see also `CompletionItemLabelDetails`) when receiving
    a completion item in a resolve call.
    """


#################################################################


class CompletionOptions(WorkDoneProgressOptions):
    trigger_characters: Optional[List[str]]
    """
    If code complete should automatically be trigger on characters not being
    valid inside an identifier (for example `.` in JavaScript) list them in
    `triggerCharacters`.
    """
    all_commit_characters: Optional[List[str]]
    """
    The list of all possible characters that commit a completion. This field
    can be used if clients don't support individual commit characters per
    completion item. See client capability
    `completion.completionItem.commitCharactersSupport`.
    """
    resolve_provider: Optional[bool]
    """
    The server provides support to resolve additional
    information for a completion item.
    """
    completion_item: Optional[OptionsCompletionItem]


class CompletionRegistrationOptions(TextDocumentRegistrationOptions, CompletionOptions):
    pass


class CompletionTriggerKind(enum.IntEnum):
    """
    * How a completion was triggered
    """

    invoked = 1
    """
    Completion was triggered by typing an identifier
    """
    trigger_character = 2
    """
    Completion was triggered by a trigger character specified by
    the `triggerCharacters` properties of the
    `CompletionRegistrationOptions
    """
    trigger_for_incomplete_completition = 3
    """
    Completion was re-triggered as the current completion list is incomplete.
    """


class CompletionContext:
    """
    * Contains additional information about the context in which a completion
    request is triggered.
    """

    trigger_kind: CompletionTriggerKind
    """
    How the completion was triggered.
    """
    trigger_character: Optional[str]
    """
    The trigger character (a single character) that has trigger code
    complete. Is undefined if
    `triggerKind !== CompletionTriggerKind.TriggerCharacter`
    """


class CompletionParams(
    TextDocumentPositionParams, WorkDoneProgressParams, PartialResultParams
):
    context: Optional[CompletionContext]


class CompletionListItemDefaultEditRange(LspModel):
    insert: Range
    replace: Range


class CompletionListItemDefault(LspModel):
    commit_characters: Optional[List[str]]
    """
    A default commit character set.
    """
    edit_range: Optional[Union[Range, CompletionListItemDefaultEditRange]]
    """
    A default edit range.
    """
    insert_text_format: Optional[InsertTextFormat]
    """
    A default insert text format.
    """
    insert_text_mode: Optional[InsertTextMode]
    """
    A default insert text mode.
    """


class CompletionList(LspModel):
    """
    * Represents a collection of [completion items](#CompletionItem) to be
    presented in the editor.
    """

    is_incomplete: bool
    """
    This list is not complete. Further typing should result in recomputing this list.
    Recomputed lists have all their items replaced (not appended) in the incomplete completion sessions.
    """
    item_defaults: Optional[CompletionListItemDefault]
    """
    In many cases the items of an actual completion result share the same
    value for properties like `commitCharacters` or the range of a text
    edit. A completion list can therefore define item defaults which will
    be used if a completion item itself doesn't specify the value.

    If a completion list specifies a default value and a completion item
    also specifies a corresponding value the one from the item is used.

    Servers are only allowed to return default values if the client
    signals support for this via the `completionList.itemDefaults` capability.
    """
    items: List["CompletionItem"]
    """
    The completion items.
    """


class InsertReplaceEdit(LspModel):
    """
    * A special text edit to provide an insert and a replace operation.
    """

    new_text: str
    """
    The string to be inserted.
    """
    insert: Range
    """
    The range if the insert is requested.
    """
    replace: Range
    """
    The range if the replace is requested.
    """


class CompletionItemLabelDetails(LspModel):
    """
    * Additional details for a completion item label.
    """

    detail: Optional[str]
    """
    An optional string which is rendered less prominently directly after
    {@link CompletionItem.label label}, without any spacing. Should be
    used for function signatures or type annotations.
    """
    description: Optional[str]
    """
    An optional string which is rendered less prominently after
    {@link CompletionItemLabelDetails.detail}. Should be used for fully qualified
    names or file path.
    """


class CompletionItem(LspModel):
    label: str
    """
    The label of this completion item.
    The label property is also by default the text that
    is inserted when selecting this completion.
    """
    label_details: Optional[CompletionItemLabelDetails]
    """
    Additional details for the label
    """
    kind: Optional[CompletionItemKind]
    """
    The kind of this completion item. Based of the kind
    an icon is chosen by the editor. The standardized set
    of available values is defined in `CompletionItemKind`.
    """
    tags: Optional[List[CompletionItemTag]]
    """
    Tags for this completion item.
    """
    detail: Optional[str]
    """
    A human-readable string with additional information
    about this item, like type or symbol information.
    """
    documentation: Optional[Union[bool, MarkupContent]]
    """
    A human-readable string that represents a doc-comment.
    """
    deprecated: Optional[bool]
    """
    Indicates if this item is deprecated.
    """
    preselect: Optional[bool]
    """
    Select this item when showing.
    """
    sort_text: Optional[str]
    """
    A string that should be used when comparing this item
    with other items. When `falsy` the label is used
    as the sort text for this item.
    """
    filter_text: Optional[str]
    """
    A string that should be used when filtering a set of
    completion items. When `falsy` the label is used as the
    filter text for this item.
    """
    insert_text: Optional[str]
    """
    A string that should be inserted into a document when selecting
    this completion. When `falsy` the label is used as the insert text
    for this item.
    """
    insert_text_format: Optional[InsertTextFormat]
    """
    The format of the insert text. The format applies to both the
    `insertText` property and the `newText` property of a provided
    `textEdit`. If omitted defaults to `InsertTextFormat.PlainText`.
    """
    insert_text_mode: Optional[InsertTextMode]
    """
    How whitespace and indentation is handled during completion
    item insertion. If not provided the client's default value depends on
    the `textDocument.completion.insertTextMode` client capability.
    """
    text_edit: Optional[Union[TextEdit, InsertReplaceEdit]]
    """
    An edit which is applied to a document when selecting this completion.
    When an edit is provided the value of `insertText` is ignored.
    """
    additional_text_edits: Optional[List[TextEdit]]
    """
    An optional array of additional text edits that are applied when
    selecting this completion. Edits must not overlap (including the same
    insert position) with the main edit nor with themselves.
    """
    commit_characters: Optional[Command]
    """
    An optional command that is executed *after* inserting this completion.
    *Note* that additional modifications to the current document should be
    described with the additionalTextEdits-property.
    """
    # LSPAny
    data: Optional[Any]
    """
    A data entry field that is preserved on a completion item between
    a completion and a completion resolve request.
    """
