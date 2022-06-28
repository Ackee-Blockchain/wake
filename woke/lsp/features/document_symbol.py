import logging
from typing import List, Optional, Union

from woke.ast.ir.declaration.abc import DeclarationAbc
from woke.lsp.common_structures import (
    DocumentSymbol,
    PartialResultParams,
    Position,
    Range,
    SymbolInformation,
    SymbolKind,
    TextDocumentIdentifier,
    TextDocumentRegistrationOptions,
    WorkDoneProgressOptions,
    WorkDoneProgressParams,
)
from woke.lsp.context import LspContext
from woke.lsp.utils.uri import uri_to_path

logger = logging.getLogger(__name__)


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


def _declaration_to_symbol(
    declaration: DeclarationAbc, kind: SymbolKind, context: LspContext
):
    byte_start, byte_end = declaration.byte_location
    start_line, start_column = context.compiler.get_line_pos_from_byte_offset(
        declaration.file, byte_start
    )
    end_line, end_column = context.compiler.get_line_pos_from_byte_offset(
        declaration.file, byte_end
    )

    name_byte_start, name_byte_end = declaration.name_location
    name_start_line, name_start_column = context.compiler.get_line_pos_from_byte_offset(
        declaration.file, name_byte_start
    )
    name_end_line, name_end_column = context.compiler.get_line_pos_from_byte_offset(
        declaration.file, name_byte_end
    )
    return DocumentSymbol(
        name=declaration.name,
        kind=kind,
        range=Range(
            start=Position(line=start_line, character=start_column),
            end=Position(line=end_line, character=end_column),
        ),
        selection_range=Range(
            start=Position(line=name_start_line, character=name_start_column),
            end=Position(line=name_end_line, character=name_end_column),
        ),
    )


async def document_symbol(
    context: LspContext, params: DocumentSymbolParams
) -> Union[List[DocumentSymbol], List[SymbolInformation], None]:
    logger.debug(f"Document symbols for file {params.text_document.uri} requested")
    await context.compiler.output_ready.wait()

    path = uri_to_path(params.text_document.uri).resolve()

    if path in context.compiler.source_units:
        source_unit = context.compiler.source_units[path]
        symbols = []

        for declared_variable in source_unit.declared_variables:
            symbols.append(
                _declaration_to_symbol(declared_variable, SymbolKind.VARIABLE, context)
            )
        for enum in source_unit.enums:
            enum_symbol = _declaration_to_symbol(enum, SymbolKind.ENUM, context)
            enum_symbol.children = []
            symbols.append(enum_symbol)
            for enum_value in enum.values:
                enum_symbol.children.append(
                    _declaration_to_symbol(enum_value, SymbolKind.ENUMMEMBER, context)
                )
        for function in source_unit.functions:
            symbols.append(
                _declaration_to_symbol(function, SymbolKind.FUNCTION, context)
            )
        for struct in source_unit.structs:
            symbols.append(_declaration_to_symbol(struct, SymbolKind.STRUCT, context))
        for error in source_unit.errors:
            symbols.append(_declaration_to_symbol(error, SymbolKind.OBJECT, context))
        for user_defined_value_type in source_unit.user_defined_value_types:
            symbols.append(
                _declaration_to_symbol(
                    user_defined_value_type, SymbolKind.OBJECT, context
                )
            )
        for contract in source_unit.contracts:
            contract_symbol = _declaration_to_symbol(
                contract, SymbolKind.CLASS, context
            )
            contract_symbol.children = []
            symbols.append(contract_symbol)
            for enum in contract.enums:
                enum_symbol = _declaration_to_symbol(enum, SymbolKind.ENUM, context)
                enum_symbol.children = []
                contract_symbol.children.append(enum_symbol)
                for enum_value in enum.values:
                    enum_symbol.children.append(
                        _declaration_to_symbol(
                            enum_value, SymbolKind.ENUMMEMBER, context
                        )
                    )
            for error in contract.errors:
                contract_symbol.children.append(
                    _declaration_to_symbol(error, SymbolKind.OBJECT, context)
                )
            for event in contract.events:
                contract_symbol.children.append(
                    _declaration_to_symbol(event, SymbolKind.EVENT, context)
                )
            for function in contract.functions:
                contract_symbol.children.append(
                    _declaration_to_symbol(function, SymbolKind.METHOD, context)
                )
            for modifier in contract.modifiers:
                contract_symbol.children.append(
                    _declaration_to_symbol(modifier, SymbolKind.FUNCTION, context)
                )
            for struct in contract.structs:
                contract_symbol.children.append(
                    _declaration_to_symbol(struct, SymbolKind.STRUCT, context)
                )
            for user_defined_value_type in contract.user_defined_value_types:
                contract_symbol.children.append(
                    _declaration_to_symbol(
                        user_defined_value_type, SymbolKind.OBJECT, context
                    )
                )
            for declared_variable in contract.declared_variables:
                contract_symbol.children.append(
                    _declaration_to_symbol(
                        declared_variable, SymbolKind.VARIABLE, context
                    )
                )
        return symbols
    return None
