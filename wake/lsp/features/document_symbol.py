import asyncio
import logging
from pathlib import Path
from typing import Callable, List, Optional, Union

from wake.core import get_logger
from wake.ir import (
    ContractDefinition,
    DeclarationAbc,
    EnumDefinition,
    ErrorDefinition,
    EventDefinition,
    FunctionDefinition,
    ModifierDefinition,
    SourceUnit,
    StructDefinition,
    UserDefinedValueTypeDefinition,
    VariableDeclaration,
)
from wake.ir.enums import ContractKind, Mutability, StateMutability
from wake.lsp.common_structures import (
    DocumentSymbol,
    PartialResultParams,
    SymbolInformation,
    TextDocumentIdentifier,
    TextDocumentRegistrationOptions,
    WorkDoneProgressOptions,
    WorkDoneProgressParams,
)
from wake.lsp.context import LspContext
from wake.lsp.utils import declaration_to_symbol_kind
from wake.lsp.utils.position import changes_to_byte_offset
from wake.lsp.utils.uri import uri_to_path

logger = get_logger(__name__)


class DocumentSymbolOptions(WorkDoneProgressOptions):
    label: Optional[str]
    """
    A human-readable string that is shown when multiple outlines trees
    are shown for the same document.
    
    @since 3.16.0
    """


class DocumentSymbolRegistrationOptions(
    TextDocumentRegistrationOptions, DocumentSymbolOptions
):
    pass


class DocumentSymbolParams(WorkDoneProgressParams, PartialResultParams):
    text_document: TextDocumentIdentifier


def _declaration_to_detail(declaration: DeclarationAbc) -> str:
    detail = ""
    if isinstance(declaration, ContractDefinition):
        if declaration.kind == ContractKind.CONTRACT:
            detail = f"{'abstract ' if declaration.abstract else ''}contract"
        elif declaration.kind == ContractKind.INTERFACE:
            detail = "interface"
        elif declaration.kind == ContractKind.LIBRARY:
            detail = "library"
    elif isinstance(declaration, EnumDefinition):
        detail = "enum"
    elif isinstance(declaration, ErrorDefinition):
        detail = "error"
    elif isinstance(declaration, EventDefinition):
        detail = "event"
    elif isinstance(declaration, FunctionDefinition):
        detail = f"{declaration.visibility} "
        if declaration.state_mutability != StateMutability.NONPAYABLE:
            detail += f"{declaration.state_mutability} "
        if declaration.virtual:
            detail += "virtual "
        if declaration.overrides is not None:
            detail += f"override "
        detail += f"function"
    elif isinstance(declaration, ModifierDefinition):
        if declaration.virtual:
            detail += "virtual "
        if declaration.overrides is not None:
            detail += f"override "
        detail += f"modifier"
    elif isinstance(declaration, StructDefinition):
        detail = "struct"
    elif isinstance(declaration, UserDefinedValueTypeDefinition):
        detail = f"is {declaration.underlying_type.name}"
    elif isinstance(declaration, VariableDeclaration):
        detail = f"{declaration.visibility} "
        if declaration.mutability != Mutability.MUTABLE:
            detail += f"{declaration.mutability} "
        if declaration.overrides is not None:
            detail += f"override "
        detail += f"variable"

    return detail


def _generate_symbols(
    source_unit: SourceUnit,
    declaration_to_symbol: Callable[[DeclarationAbc], Optional[DocumentSymbol]],
) -> List[DocumentSymbol]:
    symbols = []

    for declared_variable in source_unit.declared_variables:
        s = declaration_to_symbol(declared_variable)
        if s is not None:
            symbols.append(s)
    for enum in source_unit.enums:
        enum_symbol = declaration_to_symbol(enum)
        if enum_symbol is None:
            continue

        enum_symbol.children = []
        symbols.append(enum_symbol)
        for enum_value in enum.values:
            s = declaration_to_symbol(enum_value)
            if s is not None:
                enum_symbol.children.append(s)
    for function in source_unit.functions:
        s = declaration_to_symbol(function)
        if s is not None:
            symbols.append(s)
    for struct in source_unit.structs:
        s = declaration_to_symbol(struct)
        if s is not None:
            symbols.append(s)
    for error in source_unit.errors:
        s = declaration_to_symbol(error)
        if s is not None:
            symbols.append(s)
    for event in source_unit.events:
        s = declaration_to_symbol(event)
        if s is not None:
            symbols.append(s)
    for user_defined_value_type in source_unit.user_defined_value_types:
        s = declaration_to_symbol(user_defined_value_type)
        if s is not None:
            symbols.append(s)
    for contract in source_unit.contracts:
        contract_symbol = declaration_to_symbol(contract)
        if contract_symbol is None:
            continue

        contract_symbol.children = []
        symbols.append(contract_symbol)
        for enum in contract.enums:
            enum_symbol = declaration_to_symbol(enum)
            if enum_symbol is None:
                continue

            enum_symbol.children = []
            contract_symbol.children.append(enum_symbol)
            for enum_value in enum.values:
                s = declaration_to_symbol(enum_value)
                if s is not None:
                    enum_symbol.children.append(s)
        for error in contract.errors:
            s = declaration_to_symbol(error)
            if s is not None:
                contract_symbol.children.append(s)
        for event in contract.events:
            s = declaration_to_symbol(event)
            if s is not None:
                contract_symbol.children.append(s)
        for function in contract.functions:
            s = declaration_to_symbol(function)
            if s is not None:
                contract_symbol.children.append(s)
        for modifier in contract.modifiers:
            s = declaration_to_symbol(modifier)
            if s is not None:
                contract_symbol.children.append(s)
        for struct in contract.structs:
            s = declaration_to_symbol(struct)
            if s is not None:
                contract_symbol.children.append(s)
        for user_defined_value_type in contract.user_defined_value_types:
            s = declaration_to_symbol(user_defined_value_type)
            if s is not None:
                contract_symbol.children.append(s)
        for declared_variable in contract.declared_variables:
            s = declaration_to_symbol(declared_variable)
            if s is not None:
                contract_symbol.children.append(s)

    return symbols


def _get_document_symbol_from_cache(
    path: Path,
    context: LspContext,
):
    def declaration_to_symbol(declaration: DeclarationAbc) -> Optional[DocumentSymbol]:
        if (
            len(
                forward_changes[
                    declaration.name_location[0] : declaration.name_location[1]
                ]
            )
            > 0
        ):
            # declaration was removed
            return None

        new_byte_location_start = (
            changes_to_byte_offset(forward_changes[0 : declaration.byte_location[0]])
            + declaration.byte_location[0]
        )
        new_byte_location_end = (
            changes_to_byte_offset(forward_changes[0 : declaration.byte_location[1]])
            + declaration.byte_location[1]
        )

        new_name_location_start = (
            changes_to_byte_offset(forward_changes[0 : declaration.name_location[0]])
            + declaration.name_location[0]
        )
        new_name_location_end = (
            changes_to_byte_offset(forward_changes[0 : declaration.name_location[1]])
            + declaration.name_location[1]
        )

        return DocumentSymbol(
            name=declaration.name,
            detail=_declaration_to_detail(declaration),
            kind=declaration_to_symbol_kind(declaration),
            range=context.compiler.get_early_range_from_byte_offsets(
                path, (new_byte_location_start, new_byte_location_end)
            ),
            selection_range=context.compiler.get_early_range_from_byte_offsets(
                path, (new_name_location_start, new_name_location_end)
            ),
        )

    forward_changes = context.compiler.get_last_compilation_forward_changes(path, path)
    if forward_changes is None:
        raise Exception("No forward changes found")

    return _generate_symbols(
        context.compiler.last_compilation_source_units[path], declaration_to_symbol
    )


async def document_symbol(
    context: LspContext, params: DocumentSymbolParams
) -> Union[List[DocumentSymbol], List[SymbolInformation], None]:
    logger.debug(f"Document symbols for file {params.text_document.uri} requested")

    path = uri_to_path(params.text_document.uri).resolve()

    await next(asyncio.as_completed(
        [context.compiler.compilation_ready.wait(), context.compiler.cache_ready.wait()]
    ))

    if (
        path not in context.compiler.source_units
        or not context.compiler.compilation_ready.is_set()
    ):
        try:
            await context.compiler.cache_ready.wait()
            return _get_document_symbol_from_cache(path, context)
        except Exception:
            pass

    await context.compiler.compilation_ready.wait()

    if path in context.compiler.source_units:

        def declaration_to_symbol(declaration: DeclarationAbc) -> DocumentSymbol:
            return DocumentSymbol(
                name=declaration.name,
                detail=_declaration_to_detail(declaration),
                kind=declaration_to_symbol_kind(declaration),
                range=context.compiler.get_range_from_byte_offsets(
                    path, declaration.byte_location
                ),
                selection_range=context.compiler.get_range_from_byte_offsets(
                    path, declaration.name_location
                ),
            )

        return _generate_symbols(
            context.compiler.source_units[path], declaration_to_symbol
        )

    return None
