import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List, NamedTuple, Optional, Tuple, Union

from intervaltree import IntervalTree

from woke.ast.ir.declaration.abc import DeclarationAbc
from woke.ast.ir.declaration.contract_definition import ContractDefinition
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
        for base_function in declaration.base_functions:
            refs_count += len(base_function.references)
    elif isinstance(declaration, FunctionDefinition):
        for base_function in declaration.base_functions:
            refs_count += len(base_function.references)
        for child_function in declaration.child_functions:
            refs_count += len(child_function.references)
    elif isinstance(declaration, ModifierDefinition):
        for base_modifier in declaration.base_modifiers:
            refs_count += len(base_modifier.references)
        for child_modifier in declaration.child_modifiers:
            refs_count += len(child_modifier.references)
    return refs_count


class CodeLensCache(NamedTuple):
    original: CodeLens
    original_byte_range: Tuple[int, int]
    validity_byte_range: Tuple[int, int]


_code_lens_cache: Dict[Path, List[CodeLensCache]] = {}


def _get_code_lens_from_cache(
    context: LspContext, path: Path, tree_diff: IntervalTree
) -> Optional[List[CodeLens]]:
    if path not in _code_lens_cache:
        return None
    ret = []
    for cached_code_lens in _code_lens_cache[path]:
        changes_at_range = tree_diff[
            cached_code_lens.validity_byte_range[
                0
            ] : cached_code_lens.validity_byte_range[1]
        ]
        start, end = cached_code_lens.original_byte_range
        if len(changes_at_range) > 0:
            # changes at range, invalidate code lens
            continue
        if start == 0:
            ret.append(cached_code_lens.original)
        else:
            # recompute code lens range
            changes_before_range = tree_diff[0:start]
            byte_offset = 0
            tag: str
            j1: int
            j2: int
            for change in changes_before_range:
                tag, j1, j2 = change.data
                if tag == "insert":
                    byte_offset += j2 - j1 - 1
                elif tag == "delete":
                    byte_offset -= change.end - change.begin - 1
                elif tag == "replace":
                    byte_offset += j2 - j1 - (change.end - change.begin)
                else:
                    raise ValueError(f"Unknown tag {tag}")
            ret.append(
                CodeLens(
                    range=context.compiler.get_range_from_byte_offsets(
                        path, (start + byte_offset, end + byte_offset)
                    ),
                    command=cached_code_lens.original.command,
                    data=cached_code_lens.original.data,
                )
            )

    return ret


async def code_lens(
    context: LspContext, params: CodeLensParams
) -> Union[None, List[CodeLens]]:
    logger.debug(f"Code lens for file {params.text_document.uri} requested")
    if not context.config.lsp.code_lens.enable:
        return None
    await context.compiler.output_ready.wait()

    path = uri_to_path(params.text_document.uri).resolve()

    if path not in context.compiler.source_units:
        tree_diff = context.compiler.get_last_successful_compilation(path)
        if tree_diff is None:
            return None
        return _get_code_lens_from_cache(context, path, tree_diff)

    code_lens = []
    source_unit = context.compiler.source_units[path]

    _code_lens_cache[path] = []

    for declaration in source_unit.declarations_iter():
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
        _code_lens_cache[path].append(
            CodeLensCache(
                code_lens[-1], declaration.name_location, declaration.name_location
            )
        )

        if (
            isinstance(declaration, (FunctionDefinition, ModifierDefinition))
            and declaration.implemented
        ):
            code_lens.append(
                CodeLens(
                    range=context.compiler.get_range_from_byte_offsets(
                        declaration.file, declaration.name_location
                    ),
                    command=Command(
                        title="Control flow graph",
                        command="Tools-for-Solidity.generate.control_flow_graph",
                        arguments=[
                            params.text_document.uri,
                            declaration.canonical_name,
                        ],
                    ),
                    data=None,
                )
            )
            _code_lens_cache[path].append(
                CodeLensCache(
                    code_lens[-1], declaration.name_location, declaration.byte_location
                )
            )
        elif isinstance(declaration, ContractDefinition):
            code_lens.append(
                CodeLens(
                    range=context.compiler.get_range_from_byte_offsets(
                        declaration.file, declaration.name_location
                    ),
                    command=Command(
                        title="Inheritance graph",
                        command="Tools-for-Solidity.generate.inheritance_graph",
                        arguments=[
                            params.text_document.uri,
                            declaration.canonical_name,
                        ],
                    ),
                    data=None,
                )
            )
            _code_lens_cache[path].append(
                CodeLensCache(
                    code_lens[-1], declaration.name_location, declaration.name_location
                )
            )

            code_lens.append(
                CodeLens(
                    range=context.compiler.get_range_from_byte_offsets(
                        declaration.file, declaration.name_location
                    ),
                    command=Command(
                        title="Linearized inheritance graph",
                        command="Tools-for-Solidity.generate.linearized_inheritance_graph",
                        arguments=[
                            params.text_document.uri,
                            declaration.canonical_name,
                        ],
                    ),
                    data=None,
                )
            )
            _code_lens_cache[path].append(
                CodeLensCache(
                    code_lens[-1], declaration.name_location, declaration.name_location
                )
            )
    return code_lens
