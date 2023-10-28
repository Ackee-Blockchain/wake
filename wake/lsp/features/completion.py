from __future__ import annotations

import enum
import logging
from itertools import chain
from typing import Any, List, Optional, Union

from wake.core import get_logger

from ...compiler.source_unit_name_resolver import SourceUnitNameResolver
from ..common_structures import (
    Command,
    MarkupContent,
    MarkupKind,
    PartialResultParams,
    Position,
    Range,
    TextDocumentPositionParams,
    TextDocumentRegistrationOptions,
    TextEdit,
    WorkDoneProgressOptions,
    WorkDoneProgressParams,
)
from ..context import LspContext
from ..lsp_data_model import LspModel
from ..utils import uri_to_path

logger = get_logger(__name__)


class CompletionItemKind(enum.IntEnum):
    TEXT = 1
    METHOD = 2
    FUNCTION = 3
    CONSTRUCTOR = 4
    FIELD = 5
    VARIABLE = 6
    CLASS = 7
    INTERFACE = 8
    MODULE = 9
    PROPERTY = 10
    UNIT = 11
    VALUE = 12
    ENUM = 13
    KEYWORD = 14
    SNIPPET = 15
    COLOR = 16
    FILE = 17
    REFERENCE = 18
    FOLDER = 19
    ENUM_MEMBER = 20
    CONSTANT = 21
    STRUCT = 22
    EVENT = 23
    OPERATOR = 24
    TYPE_PARAMETER = 25


class CompletionItemTag(enum.IntEnum):
    DEPRECATED = 1
    """
    Render a completion as obsolete, usually using a strike-out.
    """


class InsertTextMode(enum.IntEnum):
    AS_IS = 1
    """
    The insertion or replace strings is taken as it is. If the
    value is multi line the lines below the cursor will be
    inserted using the indentation defined in the string value.
    The client will not apply any kind of adjustments to the
    string.
    """
    ADJUST_INDENTATION = 2
    """
    The editor adjusts leading whitespace of new lines so that
    they match the indentation up to the cursor of the line for
    which the item is accepted.
    """


class InsertTextFormat(enum.IntEnum):
    PLAIN_TEXT = 1
    """
    The primary text to be inserted is treated as a plain string.
    """
    SNIPPET = 2
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
    value_set: Optional[List[CompletionItemKind]]
    """
    If this property is not present the client only supports
    the completion items kinds from `Text` to `Reference` as defined in
    the initial version of the protocol.
    """


class ClientCapabilitiesCompletionItemInsertTextModeSupport(LspModel):
    value_set: List[InsertTextMode]


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
    documentation_format: Optional[List[MarkupKind]]
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
    insert_text_mode_support: Optional[
        ClientCapabilitiesCompletionItemInsertTextModeSupport
    ]
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

    INVOKED = 1
    """
    Completion was triggered by typing an identifier
    """
    TRIGGER_CHARACTER = 2
    """
    Completion was triggered by a trigger character specified by
    the `triggerCharacters` properties of the
    `CompletionRegistrationOptions
    """
    TRIGGER_FOR_INCOMPLETE_COMPLETIONS = 3
    """
    Completion was re-triggered as the current completion list is incomplete.
    """


class CompletionContext(LspModel):
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


class CompletionListItemDefaultsEditRange(LspModel):
    insert: Range
    replace: Range


class CompletionListItemDefaults(LspModel):
    commit_characters: Optional[List[str]]
    """
    A default commit character set.
    """
    edit_range: Optional[Union[Range, CompletionListItemDefaultsEditRange]]
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
    data: Optional[Any]
    """
    A default data value.
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
    item_defaults: Optional[CompletionListItemDefaults] = None
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
    items: List[CompletionItem]
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
    label_details: Optional[CompletionItemLabelDetails] = None
    """
    Additional details for the label
    """
    kind: Optional[CompletionItemKind] = None
    """
    The kind of this completion item. Based of the kind
    an icon is chosen by the editor. The standardized set
    of available values is defined in `CompletionItemKind`.
    """
    tags: Optional[List[CompletionItemTag]] = None
    """
    Tags for this completion item.
    """
    detail: Optional[str] = None
    """
    A human-readable string with additional information
    about this item, like type or symbol information.
    """
    documentation: Optional[Union[str, MarkupContent]] = None
    """
    A human-readable string that represents a doc-comment.
    """
    deprecated: Optional[bool] = None
    """
    Indicates if this item is deprecated.
    """
    preselect: Optional[bool] = None
    """
    Select this item when showing.
    """
    sort_text: Optional[str] = None
    """
    A string that should be used when comparing this item
    with other items. When `falsy` the label is used
    as the sort text for this item.
    """
    filter_text: Optional[str] = None
    """
    A string that should be used when filtering a set of
    completion items. When `falsy` the label is used as the
    filter text for this item.
    """
    insert_text: Optional[str] = None
    """
    A string that should be inserted into a document when selecting
    this completion. When `falsy` the label is used as the insert text
    for this item.
    """
    insert_text_format: Optional[InsertTextFormat] = None
    """
    The format of the insert text. The format applies to both the
    `insertText` property and the `newText` property of a provided
    `textEdit`. If omitted defaults to `InsertTextFormat.PlainText`.
    """
    insert_text_mode: Optional[InsertTextMode] = None
    """
    How whitespace and indentation is handled during completion
    item insertion. If not provided the client's default value depends on
    the `textDocument.completion.insertTextMode` client capability.
    """
    text_edit: Optional[Union[TextEdit, InsertReplaceEdit]] = None
    """
    An edit which is applied to a document when selecting this completion.
    When an edit is provided the value of `insertText` is ignored.
    """
    text_edit_text: Optional[str] = None
    """
    The edit text ussed if the completion item is part of a
    CompletionList and CompletionList defines an item default for
    the text edit range.
    """
    additional_text_edits: Optional[List[TextEdit]] = None
    """
    An optional array of additional text edits that are applied when
    selecting this completion. Edits must not overlap (including the same
    insert position) with the main edit nor with themselves.
    """
    commit_characters: Optional[List[str]] = None
    """
    An optional set of characters that when pressed while this completion is
    active will accept it first and then type that character. *Note* that all
    commit characters should have `length=1` and that superfluous characters
    will be ignored.
    """
    command: Optional[Command] = None
    """
    An optional command that is executed *after* inserting this completion.
    *Note* that additional modifications to the current document should be
    described with the additionalTextEdits-property.
    """
    # LSPAny
    data: Optional[Any] = None
    """
    A data entry field that is preserved on a completion item between
    a completion and a completion resolve request.
    """


async def completion(
    context: LspContext, params: CompletionParams
) -> Optional[CompletionList]:
    path = uri_to_path(params.text_document.uri).resolve()
    try:
        node = await context.parser.get_node_at_position(
            path, params.position.line, params.position.character
        )
    except KeyError:
        return None

    while node is not None:
        if node.type == "import_directive":
            break
        node = node.parent

    if node is None:
        return None

    this_source_unit_name = None
    for include_path in chain(
        context.config.compiler.solc.include_paths, [context.config.project_root_path]
    ):
        try:
            rel_path = str(path.relative_to(include_path).as_posix())
            if this_source_unit_name is None or len(this_source_unit_name) > len(
                rel_path
            ):
                this_source_unit_name = rel_path
        except ValueError:
            continue

    if this_source_unit_name is None:
        return None

    source_node = node.child_by_field_name("source")
    import_str = source_node.text.decode("utf-16-le")[1:-1]  # remove quotes
    resolver = SourceUnitNameResolver(context.config)
    import_str = resolver.apply_remapping(this_source_unit_name, import_str)

    parts = import_str.split("/")
    parent = "/".join(parts[:-1])
    prefix = parts[-1]

    completions = set()

    if len(parent) == 0:
        for p in path.parent.iterdir():
            if p.is_dir():
                completions.add(("./" + p.name + "/", CompletionItemKind.FOLDER))
            elif p.is_file() and p.suffix == ".sol" and p != path:
                completions.add(("./" + p.name, CompletionItemKind.FILE))

        for include_path in chain(
            context.config.compiler.solc.include_paths,
            [context.config.project_root_path],
        ):
            if include_path.is_dir():
                for p in include_path.iterdir():
                    if p.is_dir():
                        completions.add((p.name + "/", CompletionItemKind.FOLDER))
                    elif p.is_file() and p.suffix == ".sol":
                        completions.add((p.name, CompletionItemKind.FILE))

        for remapping in context.config.compiler.solc.remappings:
            if remapping.context is None or this_source_unit_name.startswith(
                remapping.context
            ):
                completions.add((remapping.prefix, CompletionItemKind.MODULE))

    elif parent.startswith("."):
        dir = path.parent / parent
        if dir.is_dir():
            for p in dir.iterdir():
                if p.is_dir():
                    completions.add((p.name + "/", CompletionItemKind.FOLDER))
                elif p.is_file() and p.suffix == ".sol" and p != path:
                    completions.add((p.name, CompletionItemKind.FILE))
    else:
        for include_path in chain(
            context.config.compiler.solc.include_paths,
            [context.config.project_root_path],
        ):
            if include_path.is_dir():
                dir = include_path / parent
                if dir.is_dir():
                    for p in dir.iterdir():
                        if p.is_dir():
                            completions.add((p.name + "/", CompletionItemKind.FOLDER))
                        elif p.is_file() and p.suffix == ".sol":
                            completions.add((p.name, CompletionItemKind.FILE))

    import_end_pos = Position(
        line=source_node.end_point[0],
        character=source_node.end_point[1] // 2 - 1,
    )

    return CompletionList(
        is_incomplete=False,
        items=[
            CompletionItem(
                label=l,
                kind=k,
                text_edit=TextEdit(
                    range=Range(
                        start=import_end_pos,
                        end=import_end_pos,
                    ),
                    new_text=l[len(prefix) :],
                ),
            )
            for l, k in sorted(completions)  # pyright: ignore reportGeneralTypeIssues
            if l.startswith(prefix)
        ],
    )


CompletionList.update_forward_refs()
