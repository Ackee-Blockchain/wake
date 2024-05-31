from enum import IntEnum
from typing import Any, List, Optional, Union

from wake.utils import StrEnum

from ..common_structures import (
    Command,
    Diagnostic,
    PartialResultParams,
    Position,
    Range,
    TextDocumentIdentifier,
    TextEdit,
    WorkDoneProgressOptions,
    WorkDoneProgressParams,
    WorkspaceEdit,
)
from ..context import LspContext
from ..lsp_data_model import LspModel
from ..utils import uri_to_path


class CodeActionKind(StrEnum):
    EMPTY = ""
    QUICKFIX = "quickfix"
    REFACTOR = "refactor"
    REFACTOR_EXTRACT = "refactor.extract"
    REFACTOR_INLINE = "refactor.inline"
    REFACTOR_REWRITE = "refactor.rewrite"
    SOURCE = "source"
    SOURCE_ORGANIZE_IMPORTS = "source.organizeImports"
    SOURCE_FIX_ALL = "source.fixAll"


class CodeActionTriggerKind(IntEnum):
    INVOKED = 1
    AUTOMATIC = 2


class CodeActionOptions(WorkDoneProgressOptions):
    code_action_kinds: Optional[List[CodeActionKind]] = None
    resolve_provider: Optional[bool] = None


class CodeActionContext(LspModel):
    diagnostics: List[Diagnostic]
    only: Optional[List[CodeActionKind]] = None
    trigger_kind: Optional[CodeActionTriggerKind] = None


class CodeActionParams(WorkDoneProgressParams, PartialResultParams):
    text_document: TextDocumentIdentifier
    range: Range
    context: CodeActionContext


class CodeActionDisabled(LspModel):
    reason: str


class CodeAction(LspModel):
    title: str
    kind: Optional[CodeActionKind]
    diagnostics: Optional[List[Diagnostic]]
    is_preferred: Optional[bool]
    disabled: Optional[CodeActionDisabled] = None
    edit: Optional[WorkspaceEdit]
    command: Optional[Command] = None
    data: Optional[Any] = None


async def code_action(
    context: LspContext, params: CodeActionParams
) -> Optional[List[Union[Command, CodeAction]]]:
    path = uri_to_path(params.text_document.uri).resolve()
    line_ending = context.parser.get_line_ending(path)
    if line_ending is None:
        line_ending = "\n"

    ret = []

    for diag in params.context.diagnostics:
        try:
            node = await context.parser.get_node_at_position(
                path, diag.range.start.line, diag.range.start.character
            )
        except KeyError:
            continue

        if diag.code in {4937, "4937"}:
            # No visibility specified. Did you intend to add "public"?
            while node is not None:
                if node.type == "function_definition":
                    break
                node = node.parent

            if node is None or any(
                child.type == "visibility" for child in node.children
            ):
                continue

            for child in node.children:
                if child.type == ")":
                    pos = Position(
                        line=child.end_point[0], character=child.end_point[1] // 2
                    )
                    range = Range(start=pos, end=pos)
                    for visibility in ["public", "private", "external", "internal"]:
                        ret.append(
                            CodeAction(
                                title=f"Add {visibility} visibility",
                                kind=CodeActionKind.QUICKFIX,
                                diagnostics=[diag],
                                is_preferred=visibility == "public",
                                edit=WorkspaceEdit(
                                    changes={
                                        params.text_document.uri: [
                                            TextEdit(
                                                range=range, new_text=f" {visibility}"
                                            )
                                        ]
                                    }
                                ),
                            )
                        )
        elif diag.code in {2018, "2018"}:
            # Function state mutability can be restricted to pure/view
            if "pure" in diag.message:
                mutability = "pure"
            elif "view" in diag.message:
                mutability = "view"
            else:
                continue

            while node is not None:
                if node.type == "function_definition":
                    break
                node = node.parent

            if node is None or any(
                child.type == "state_mutability" for child in node.children
            ):
                continue

            children = [
                child for child in node.children if child.type in {"visibility", ")"}
            ]
            if len(children) == 0:
                continue
            if len(children) > 1:
                child = next(c for c in children if c.type == "visibility")
            else:
                child = children[0]

            pos = Position(line=child.end_point[0], character=child.end_point[1] // 2)
            ret.append(
                CodeAction(
                    title=f"Add {mutability} mutability",
                    kind=CodeActionKind.QUICKFIX,
                    diagnostics=[diag],
                    is_preferred=True,
                    edit=WorkspaceEdit(
                        changes={
                            params.text_document.uri: [
                                TextEdit(
                                    range=Range(start=pos, end=pos),
                                    new_text=f" {mutability}",
                                )
                            ]
                        }
                    ),
                )
            )
        elif diag.code in {1878, "1878"}:
            # SPDX license identifier not provided in source file
            for license in [
                "MIT",
                "Apache-2.0",
                "GPL-3.0",
                "BSD-3-Clause",
                "CC0-1.0",
                "UNLICENSED",
            ]:
                ret.append(
                    CodeAction(
                        title=f"Add SPDX license identifier {license}",
                        kind=CodeActionKind.QUICKFIX,
                        diagnostics=[diag],
                        is_preferred=license == "MIT",
                        edit=WorkspaceEdit(
                            changes={
                                params.text_document.uri: [
                                    TextEdit(
                                        range=Range(
                                            start=Position(line=0, character=0),
                                            end=Position(line=0, character=0),
                                        ),
                                        new_text=f"// SPDX-License-Identifier: {license}{line_ending}",
                                    )
                                ]
                            }
                        ),
                    )
                )

    if len(ret) == 0:
        return None
    return ret
