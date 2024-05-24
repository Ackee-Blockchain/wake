from wake.ir import (
    DeclarationAbc,
    ContractDefinition,
    EnumDefinition,
    EnumValue,
    ErrorDefinition,
    EventDefinition,
    FunctionDefinition,
    ModifierDefinition,
    StructDefinition,
    VariableDeclaration,
    UserDefinedValueTypeDefinition,
)
from wake.ir.enums import ContractKind, FunctionKind, Mutability
from wake.lsp.common_structures import SymbolKind


def declaration_to_symbol_kind(declaration: DeclarationAbc) -> SymbolKind:
    if isinstance(declaration, ContractDefinition):
        if declaration.kind == ContractKind.INTERFACE:
            return SymbolKind.INTERFACE
        else:
            return SymbolKind.CLASS
    elif isinstance(declaration, EnumDefinition):
        return SymbolKind.ENUM
    elif isinstance(declaration, EnumValue):
        return SymbolKind.ENUMMEMBER
    elif isinstance(declaration, ErrorDefinition):
        return SymbolKind.OBJECT
    elif isinstance(declaration, EventDefinition):
        return SymbolKind.EVENT
    elif isinstance(declaration, FunctionDefinition):
        if declaration.kind == FunctionKind.CONSTRUCTOR:
            return SymbolKind.CONSTRUCTOR
        elif isinstance(declaration.parent, ContractDefinition):
            return SymbolKind.METHOD
        else:
            return SymbolKind.FUNCTION
    elif isinstance(declaration, ModifierDefinition):
        return SymbolKind.METHOD
    elif isinstance(declaration, StructDefinition):
        return SymbolKind.STRUCT
    elif isinstance(declaration, UserDefinedValueTypeDefinition):
        return SymbolKind.OBJECT
    elif isinstance(declaration, VariableDeclaration):
        if declaration.mutability in {
            Mutability.CONSTANT,
            Mutability.IMMUTABLE,
        }:
            return SymbolKind.CONSTANT
        else:
            return SymbolKind.VARIABLE
    else:
        raise ValueError(f"Unknown declaration type {type(declaration)}")
