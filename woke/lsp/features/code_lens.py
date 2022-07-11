import logging
from typing import Any, Iterable, List, Optional, Tuple, Union

from woke.ast.ir.declaration.abc import DeclarationAbc
from woke.ast.ir.declaration.function_definition import FunctionDefinition
from woke.ast.ir.declaration.modifier_definition import ModifierDefinition
from woke.ast.ir.declaration.variable_declaration import VariableDeclaration
from woke.ast.ir.expression.identifier import Identifier
from woke.ast.ir.expression.member_access import MemberAccess
from woke.ast.ir.meta.identifier_path import IdentifierPath
from woke.ast.ir.type_name.user_defined_type_name import UserDefinedTypeName
from woke.lsp.common_structures import (
    Command,
    DocumentUri,
    Location,
    PartialResultParams,
    Position,
    Range,
    TextDocumentIdentifier,
    TextDocumentRegistrationOptions,
    WorkDoneProgressOptions,
    WorkDoneProgressParams,
)
from woke.lsp.context import LspContext
from woke.lsp.lsp_data_model import LspModel
from woke.lsp.utils.uri import path_to_uri, uri_to_path

logger = logging.getLogger(__name__)


class CodeLensOptions(WorkDoneProgressOptions):
    resolve_provider: Optional[bool]
    """
    Code lens has a resolve provider as well.
    """


class CodeLensRegistrationOptions(TextDocumentRegistrationOptions, CodeLensOptions):
    pass


class CodeLensParams(WorkDoneProgressParams, PartialResultParams):
    text_document: TextDocumentIdentifier
    """
    The document to request code lens for.
    """


class CodeLens(LspModel):
    """
    A code lens represents a command that should be shown along with
    source text, like the number of references, a way to run tests, etc.

    A code lens is _unresolved_ when no command is associated to it. For
    performance reasons the creation of a code lens and resolving should be done
    in two stages
    """

    range: Range
    """
    The range in which this code lens is valid. Should only span a single line.
    """
    command: Optional[Command]
    """
    The command this code lens represents.
    """
    data: Optional[Any]
    """
    A data entry field that is preserved on a code lens item between
    a code lens and a code lens resolve request.
    """


def _resolve_declaration(declaration: DeclarationAbc, context: LspContext) -> int:
    refs_count = len(declaration.references)

    if isinstance(declaration, VariableDeclaration):
        if declaration.base_functions is not None:
            for base_function in declaration.base_functions:
                refs_count += len(base_function.references)
    elif isinstance(declaration, FunctionDefinition):
        if declaration.base_functions is not None:
            for base_function in declaration.base_functions:
                refs_count += len(base_function.references)
        for child_function in declaration.child_functions:
            refs_count += len(child_function.references)
    elif isinstance(declaration, ModifierDefinition):
        if declaration.base_modifiers is not None:
            for base_modifier in declaration.base_modifiers:
                refs_count += len(base_modifier.references)
        for child_modifier in declaration.child_modifiers:
            refs_count += len(child_modifier.references)
    return refs_count


async def code_lens(
    context: LspContext, params: CodeLensParams
) -> Union[None, List[CodeLens]]:
    logger.debug(f"Code lens for file {params.text_document.uri} requested")
    await context.compiler.output_ready.wait()

    path = uri_to_path(params.text_document.uri).resolve()

    if path not in context.compiler.source_units:
        return None

    code_lens = []
    source_unit = context.compiler.source_units[path]

    for declaration in source_unit.declarations:
        refs_count = _resolve_declaration(declaration, context)
        code_lens.append(
            CodeLens(
                range=context.compiler.get_range_from_byte_offsets(
                    declaration.file, declaration.name_location
                ),
                command=Command(
                    title=f"{refs_count} references"
                    if refs_count != 1
                    else "1 reference",
                    command="",
                    arguments=None,
                ),
                data=None,
            )
        )
    return code_lens
