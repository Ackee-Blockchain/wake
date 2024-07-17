import asyncio
from typing import List

from wake.ir import ContractDefinition
from wake.lsp.common_structures import (
    Location,
    WorkspaceSymbol,
    WorkspaceSymbolParams,
    WorkspaceSymbolUriLocation,
)
from wake.lsp.context import LspContext
from wake.lsp.exceptions import LspError
from wake.lsp.protocol_structures import ErrorCodes
from wake.lsp.utils import declaration_to_symbol_kind, path_to_uri, uri_to_path
from wake.lsp.utils.position import changes_to_byte_offset


async def workspace_symbol(
    context: LspContext, params: WorkspaceSymbolParams
) -> List[WorkspaceSymbol]:
    query = params.query.lower()
    declarations = []

    await next(
        asyncio.as_completed(
            [
                context.compiler.compilation_ready.wait(),
                context.compiler.cache_ready.wait(),
            ]
        )
    )

    if not context.compiler.compilation_ready.is_set():
        for path, source_unit in context.compiler.last_compilation_source_units.items():
            if path not in context.compiler.early_opened_files and not path.exists():
                continue

            declarations.extend(
                decl
                for decl in source_unit.declarations_iter()
                if query in decl.name.lower()
            )
    else:
        for source_unit in context.compiler.source_units.values():
            declarations.extend(
                decl
                for decl in source_unit.declarations_iter()
                if query in decl.name.lower()
            )

        await context.compiler.cache_ready.wait()

        # also process files that could not be compiled in the last run but still exist
        for path, source_unit in context.compiler.last_compilation_source_units.items():
            if path not in context.compiler.source_units and (
                path in context.compiler.early_opened_files or path.exists()
            ):
                declarations.extend(
                    decl
                    for decl in source_unit.declarations_iter()
                    if query in decl.name.lower()
                )

    symbols = []
    for decl in declarations:
        symbols.append(
            (
                WorkspaceSymbol(
                    name=decl.name,
                    kind=declaration_to_symbol_kind(decl),
                    container_name=decl.parent.name
                    if isinstance(decl.parent, ContractDefinition)
                    else None,
                    location=WorkspaceSymbolUriLocation(
                        uri=path_to_uri(decl.source_unit.file)
                    ),
                ),
                decl.source_unit.source_unit_name,
            )
        )

    symbols.sort(key=lambda x: (x[0].name, x[1]))
    return [x[0] for x in symbols]


async def workspace_symbol_resolve(
    context: LspContext, symbol: WorkspaceSymbol
) -> WorkspaceSymbol:
    if not isinstance(symbol.location, WorkspaceSymbolUriLocation):
        return symbol

    path = uri_to_path(symbol.location.uri)

    await next(asyncio.as_completed(
        [context.compiler.compilation_ready.wait(), context.compiler.cache_ready.wait()]
    ))

    forward_changes = context.compiler.get_last_compilation_forward_changes(path, path)
    cache_checked = False

    if (
        not context.compiler.compilation_ready.is_set()
        and forward_changes is not None
        and path in context.compiler.last_compilation_source_units
    ):
        cache_checked = True
        for decl in context.compiler.last_compilation_source_units[
            path
        ].declarations_iter():
            if decl.name != symbol.name:
                continue

            parent_name = (
                decl.parent.name
                if isinstance(decl.parent, ContractDefinition)
                else None
            )
            if parent_name != symbol.container_name:
                continue

            new_byte_start = (
                changes_to_byte_offset(forward_changes[0 : decl.byte_location[0]])
                + decl.byte_location[0]
            )
            new_byte_end = (
                changes_to_byte_offset(forward_changes[0 : decl.byte_location[1]])
                + decl.byte_location[1]
            )

            symbol.location = Location(
                uri=path_to_uri(path),
                range=context.compiler.get_early_range_from_byte_offsets(
                    path, (new_byte_start, new_byte_end)
                ),
            )
            return symbol

    await context.compiler.compilation_ready.wait()

    if path in context.compiler.source_units:
        for decl in context.compiler.source_units[path].declarations_iter():
            if decl.name != symbol.name:
                continue

            parent_name = (
                decl.parent.name
                if isinstance(decl.parent, ContractDefinition)
                else None
            )
            if parent_name != symbol.container_name:
                continue

            symbol.location = Location(
                uri=path_to_uri(path),
                range=context.compiler.get_range_from_byte_offsets(
                    path, decl.byte_location
                ),
            )
            return symbol

    if cache_checked:
        raise LspError(ErrorCodes.InvalidParams, f"Unknown symbol {symbol.name}")

    await context.compiler.cache_ready.wait()
    forward_changes = context.compiler.get_last_compilation_forward_changes(path, path)

    if (
        forward_changes is not None
        and (path in context.compiler.early_opened_files or path.exists())
        and path in context.compiler.last_compilation_source_units
    ):
        for decl in context.compiler.last_compilation_source_units[
            path
        ].declarations_iter():
            if decl.name != symbol.name:
                continue

            parent_name = (
                decl.parent.name
                if isinstance(decl.parent, ContractDefinition)
                else None
            )
            if parent_name != symbol.container_name:
                continue

            new_byte_start = (
                changes_to_byte_offset(forward_changes[0 : decl.byte_location[0]])
                + decl.byte_location[0]
            )
            new_byte_end = (
                changes_to_byte_offset(forward_changes[0 : decl.byte_location[1]])
                + decl.byte_location[1]
            )

            symbol.location = Location(
                uri=path_to_uri(path),
                range=context.compiler.get_early_range_from_byte_offsets(
                    path, (new_byte_start, new_byte_end)
                ),
            )
            return symbol

    raise LspError(ErrorCodes.InvalidParams, f"Unknown symbol {symbol.name}")
