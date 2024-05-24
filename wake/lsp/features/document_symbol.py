import logging
from typing import List, Optional, Union

from wake.core import get_logger
from wake.ir import (
    ContractDefinition,
    DeclarationAbc,
    EnumDefinition,
    ErrorDefinition,
    EventDefinition,
    FunctionDefinition,
    ModifierDefinition,
    StructDefinition,
    UserDefinedValueTypeDefinition,
    VariableDeclaration,
)
from wake.ir.enums import ContractKind, Mutability, StateMutability
from wake.lsp.common_structures import (
    DocumentSymbol,
    PartialResultParams,
    SymbolInformation,
    SymbolKind,
    TextDocumentIdentifier,
    TextDocumentRegistrationOptions,
    WorkDoneProgressOptions,
    WorkDoneProgressParams,
)
from wake.lsp.context import LspContext
from wake.lsp.utils import declaration_to_symbol_kind
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


def _declaration_to_symbol(declaration: DeclarationAbc, context: LspContext):
    kind = declaration_to_symbol_kind(declaration)
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

    file = declaration.source_unit.file
    return DocumentSymbol(
        name=declaration.name,
        detail=detail,
        kind=kind,
        range=context.compiler.get_range_from_byte_offsets(
            file, declaration.byte_location
        ),
        selection_range=context.compiler.get_range_from_byte_offsets(
            file, declaration.name_location
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
            symbols.append(_declaration_to_symbol(declared_variable, context))
        for enum in source_unit.enums:
            enum_symbol = _declaration_to_symbol(enum, context)
            enum_symbol.children = []
            symbols.append(enum_symbol)
            for enum_value in enum.values:
                enum_symbol.children.append(_declaration_to_symbol(enum_value, context))
        for function in source_unit.functions:
            symbols.append(_declaration_to_symbol(function, context))
        for struct in source_unit.structs:
            symbols.append(_declaration_to_symbol(struct, context))
        for error in source_unit.errors:
            symbols.append(_declaration_to_symbol(error, context))
        for event in source_unit.events:
            symbols.append(_declaration_to_symbol(event, context))
        for user_defined_value_type in source_unit.user_defined_value_types:
            symbols.append(_declaration_to_symbol(user_defined_value_type, context))
        for contract in source_unit.contracts:
            contract_symbol = _declaration_to_symbol(contract, context)
            contract_symbol.children = []
            symbols.append(contract_symbol)
            for enum in contract.enums:
                enum_symbol = _declaration_to_symbol(enum, context)
                enum_symbol.children = []
                contract_symbol.children.append(enum_symbol)
                for enum_value in enum.values:
                    enum_symbol.children.append(
                        _declaration_to_symbol(enum_value, context)
                    )
            for error in contract.errors:
                contract_symbol.children.append(_declaration_to_symbol(error, context))
            for event in contract.events:
                contract_symbol.children.append(_declaration_to_symbol(event, context))
            for function in contract.functions:
                contract_symbol.children.append(
                    _declaration_to_symbol(function, context)
                )
            for modifier in contract.modifiers:
                contract_symbol.children.append(
                    _declaration_to_symbol(modifier, context)
                )
            for struct in contract.structs:
                contract_symbol.children.append(_declaration_to_symbol(struct, context))
            for user_defined_value_type in contract.user_defined_value_types:
                contract_symbol.children.append(
                    _declaration_to_symbol(user_defined_value_type, context)
                )
            for declared_variable in contract.declared_variables:
                if declared_variable.mutability in {
                    Mutability.IMMUTABLE,
                    Mutability.CONSTANT,
                }:
                    contract_symbol.children.append(
                        _declaration_to_symbol(declared_variable, context)
                    )
                else:
                    contract_symbol.children.append(
                        _declaration_to_symbol(declared_variable, context)
                    )
        return symbols
    return None
