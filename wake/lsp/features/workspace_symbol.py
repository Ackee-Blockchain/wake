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


async def workspace_symbol(
    context: LspContext, params: WorkspaceSymbolParams
) -> List[WorkspaceSymbol]:
    await context.compiler.output_ready.wait()

    query = params.query.lower()
    symbols = []

    for source_unit in context.compiler.source_units.values():
        for decl in source_unit.declarations_iter():
            if query not in decl.name.lower():
                continue

            symbols.append(
                (
                    WorkspaceSymbol(
                        name=decl.name,
                        kind=declaration_to_symbol_kind(decl),
                        container_name=decl.parent.name
                        if isinstance(decl.parent, ContractDefinition)
                        else None,
                        location=WorkspaceSymbolUriLocation(
                            uri=path_to_uri(source_unit.file)
                        ),
                    ),
                    source_unit,
                )
            )

    symbols.sort(key=lambda x: (x[0].name, x[1].source_unit_name))
    return [x[0] for x in symbols]


async def workspace_symbol_resolve(
    context: LspContext, symbol: WorkspaceSymbol
) -> WorkspaceSymbol:
    await context.compiler.output_ready.wait()

    if not isinstance(symbol.location, WorkspaceSymbolUriLocation):
        return symbol

    path = uri_to_path(symbol.location.uri)
    if path not in context.compiler.source_units:
        raise LspError(ErrorCodes.InvalidParams, f"Unknown file {path}")

    found = False
    for decl in context.compiler.source_units[path].declarations_iter():
        if decl.name != symbol.name:
            continue

        parent_name = (
            decl.parent.name if isinstance(decl.parent, ContractDefinition) else None
        )
        if parent_name != symbol.container_name:
            continue

        found = True
        symbol.location = Location(
            uri=path_to_uri(path),
            range=context.compiler.get_range_from_byte_offsets(
                path, decl.byte_location
            ),
        )

    if not found:
        raise LspError(ErrorCodes.InvalidParams, f"Unknown symbol {symbol.name}")

    return symbol
