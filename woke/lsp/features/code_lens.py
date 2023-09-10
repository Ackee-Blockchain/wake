import logging
import os
from collections import defaultdict
from pathlib import Path
from typing import (
    Any,
    DefaultDict,
    Dict,
    List,
    NamedTuple,
    Optional,
    Tuple,
    Type,
    Union,
)

import rich_click as click
from intervaltree import IntervalTree
from rich import get_console
from rich.terminal_theme import MONOKAI

from woke.cli.print import run_print
from woke.core.visitor import visit_map
from woke.ir import (
    ContractDefinition,
    DeclarationAbc,
    ErrorDefinition,
    EventDefinition,
    FunctionDefinition,
    IrAbc,
    ModifierDefinition,
    VariableDeclaration,
)
from woke.lsp.common_structures import (
    Command,
    MessageType,
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
from woke.lsp.utils.position import changes_to_byte_offset
from woke.lsp.utils.uri import uri_to_path
from woke.printers.api import Printer, get_printers

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
    context: LspContext, path: Path, forward_changes: IntervalTree
) -> Optional[List[CodeLens]]:
    if path not in _code_lens_cache:
        return None
    ret = []
    for cached_code_lens in _code_lens_cache[path]:
        changes_at_range = forward_changes[
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
            new_start = changes_to_byte_offset(forward_changes[0:start]) + start
            new_end = changes_to_byte_offset(forward_changes[0:end]) + end
            ret.append(
                CodeLens(
                    range=context.compiler.get_range_from_byte_offsets(
                        path, (new_start, new_end)
                    ),
                    command=cached_code_lens.original.command,
                    data=cached_code_lens.original.data,
                )
            )

    return ret


def _get_printer_output(
    context: LspContext,
    printer_name: str,
    command: click.Command,
    printer_cls: Type[Printer],
    node: IrAbc,
) -> Optional[str]:
    if hasattr(context.config.printers, printer_name):
        default_map = getattr(context.config.printers, printer_name)
    else:
        default_map = None

    console = get_console()
    original_record = console.record
    original_file = console.file

    console.record = True
    console.file = open(os.devnull, "w")

    def _callback(*args, **kwargs):
        instance.paths = [Path(p).resolve() for p in kwargs.pop("paths", [])]

        original_callback(
            instance, *args, **kwargs
        )  # pyright: ignore reportOptionalCall

    instance = printer_cls()
    instance.build = context.compiler.last_build
    instance.build_info = context.compiler.last_build_info
    instance.config = context.config
    instance.console = console
    instance.imports_graph = (  # pyright: ignore reportGeneralTypeIssues
        context.compiler.last_graph.copy()
    )

    original_callback = command.callback
    command.callback = _callback

    try:
        sub_ctx = command.make_context(
            command.name,
            [],
            default_map=default_map,
        )
        with sub_ctx:
            sub_ctx.command.invoke(sub_ctx)

        if not instance.lsp_predicate(node):
            command.callback = original_callback
            return None

        # call the target visit function with the node
        visit_map[node.ast_node.node_type](instance, node)

        instance.print()
    finally:
        command.callback = original_callback

    # TODO detect theme from VS Code settings?
    ret = console.export_html(theme=MONOKAI)
    console.record = original_record
    console.file = original_file
    return ret


def _generate_code_lens(
    context: LspContext,
    path: Path,
    title: str,
    command: str,
    arguments: Optional[List],
    byte_range: Tuple[int, int],
    validity_range: Tuple[int, int],
) -> CodeLens:
    ret = CodeLens(
        range=context.compiler.get_range_from_byte_offsets(path, byte_range),
        command=Command(
            title=title,
            command=command,
            arguments=arguments,
        ),
        data=None,
    )
    _code_lens_cache[path].append(CodeLensCache(ret, byte_range, validity_range))
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
        forward_changes = context.compiler.get_last_compilation_forward_changes(path)
        if forward_changes is None:
            return None
        return _get_code_lens_from_cache(context, path, forward_changes)

    code_lens: List[CodeLens] = []
    source_unit = context.compiler.source_units[path]

    _code_lens_cache[path] = []

    printers: DefaultDict[
        Type[IrAbc], Dict[str, Tuple[click.Command, Type[Printer]]]
    ] = defaultdict(dict)
    for printer_name, printer in get_printers(
        {context.config.project_root_path / "printers"},
        False,
    ).items():
        lsp_node = printer[1].lsp_node()
        if lsp_node is None:
            continue
        if isinstance(lsp_node, (list, tuple)):
            for node in lsp_node:
                printers[node][printer_name] = printer
        else:
            printers[lsp_node][printer_name] = printer

    for (
        package,
        e,
    ) in (
        run_print.failed_plugin_entry_points  # pyright: ignore reportGeneralTypeIssues
    ):
        await context.server.show_message(
            f"Failed to load printers from package {package}: {e}", MessageType.ERROR
        )
        await context.server.log_message(
            f"Failed to load printers from package {package}: {e}", MessageType.ERROR
        )
    for (
        path,
        e,
    ) in run_print.failed_plugin_paths:  # pyright: ignore reportGeneralTypeIssues
        await context.server.show_message(
            f"Failed to load printers from path {path}: {e}", MessageType.ERROR
        )
        await context.server.log_message(
            f"Failed to load printers from path {path}: {e}", MessageType.ERROR
        )

    for node in source_unit:
        if isinstance(node, DeclarationAbc):
            refs = list(node.get_all_references(include_declarations=True))
            refs_count = len(
                [ref for ref in refs if not isinstance(ref, DeclarationAbc)]
            )
            declaration_positions = []

            for ref in refs:
                if isinstance(ref, DeclarationAbc):
                    line, col = context.compiler.get_line_pos_from_byte_offset(
                        ref.file, ref.name_location[0]
                    )
                    declaration_positions.append(Position(line=line, character=col))

            line, col = context.compiler.get_line_pos_from_byte_offset(
                node.file, node.name_location[0]
            )

            # should include info to be able to recover command args from cache (positions could have changed)
            # but references do not work in cache mode (compilation error) anyway
            code_lens.append(
                _generate_code_lens(
                    context,
                    node.file,
                    f"{refs_count} references" if refs_count != 1 else "1 reference",
                    "Tools-for-Solidity.execute.references",
                    [
                        params.text_document.uri,
                        Position(line=line, character=col),
                        declaration_positions,
                    ],
                    node.name_location,
                    node.name_location,
                )
            )

            if (
                isinstance(node, (FunctionDefinition, ModifierDefinition))
                and node.implemented
            ):
                code_lens.append(
                    _generate_code_lens(
                        context,
                        node.file,
                        "Control flow graph",
                        "Tools-for-Solidity.generate.control_flow_graph",
                        [params.text_document.uri, node.canonical_name],
                        node.name_location,
                        node.byte_location,
                    )
                )
            elif isinstance(node, ContractDefinition):
                code_lens.append(
                    _generate_code_lens(
                        context,
                        node.file,
                        "Inheritance graph",
                        "Tools-for-Solidity.generate.inheritance_graph",
                        [params.text_document.uri, node.canonical_name],
                        node.name_location,
                        node.name_location,
                    )
                )

                code_lens.append(
                    _generate_code_lens(
                        context,
                        node.file,
                        "Linearized inheritance graph",
                        "Tools-for-Solidity.generate.linearized_inheritance_graph",
                        [params.text_document.uri, node.canonical_name],
                        node.name_location,
                        node.name_location,
                    )
                )

            if (
                isinstance(node, FunctionDefinition)
                and node.function_selector is not None
            ):
                code_lens.append(
                    _generate_code_lens(
                        context,
                        node.file,
                        f"{node.function_selector.hex()}",
                        "Tools-for-Solidity.copy_to_clipboard",
                        [node.function_selector.hex()],
                        node.name_location,
                        node.byte_location,
                    )
                )
            elif isinstance(node, ErrorDefinition) and node.error_selector is not None:
                code_lens.append(
                    _generate_code_lens(
                        context,
                        node.file,
                        f"{node.error_selector.hex()}",
                        "Tools-for-Solidity.copy_to_clipboard",
                        [node.error_selector.hex()],
                        node.name_location,
                        node.byte_location,
                    )
                )
            elif isinstance(node, EventDefinition) and node.event_selector is not None:
                code_lens.append(
                    _generate_code_lens(
                        context,
                        node.file,
                        f"{node.event_selector.hex()}",
                        "Tools-for-Solidity.copy_to_clipboard",
                        [node.event_selector.hex()],
                        node.name_location,
                        node.byte_location,
                    )
                )

        for printer_name in sorted(printers[node.__class__].keys()):
            command, printer_cls = printers[node.__class__][printer_name]

            try:
                out = _get_printer_output(
                    context, printer_name, command, printer_cls, node
                )
            except Exception as e:
                await context.server.show_message(
                    f"Error while running printer {printer_name}: {e}",
                    MessageType.ERROR,
                )
                await context.server.log_message(
                    f"Error while running printer {printer_name}: {e}",
                    MessageType.ERROR,
                )
                out = None

            if out is not None:
                code_lens.append(
                    _generate_code_lens(
                        context,
                        node.file,
                        printer_name,  # TODO make command name configurable from printer?
                        "Tools-for-Solidity.printer",
                        [
                            printer_name,
                            out,
                        ],
                        node.name_location
                        if isinstance(node, DeclarationAbc)
                        else node.byte_location,
                        node.byte_location,
                    )
                )

    code_lens.sort(
        key=lambda x: (
            x.range.start.line,
            x.range.start.character,
            x.range.end.line,
            x.range.end.character,
        )
    )
    return code_lens
