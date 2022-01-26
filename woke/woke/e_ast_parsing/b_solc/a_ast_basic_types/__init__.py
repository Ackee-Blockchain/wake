from typing import Dict, List, Optional, TypedDict

from pydantic.types import StrictBool, StrictInt, StrictStr

# Comments are the first ocurrence per the ordering in the definition file

# SolcNode
Id = StrictInt
Src = StrictStr

# SolcSourceUnit
SourceLocation = StrictStr
AbsolutePath = StrictStr
ExportedSymbols = Dict[StrictStr, List[StrictInt]]
# optional
License = StrictStr

# SolcPragmaDirective
Literals = List[StrictStr]

# SolcImportDirective
File = StrictStr
Scope = StrictInt
SourceUnit = StrictInt
UnitAlias = StrictStr
# optional
NameLocation = StrictStr

# VariableDeclaration
Name = StrictStr
Constant = StrictBool
FunctionSelector = StrictStr
Indexed = StrictBool
StateVariable = StrictBool
# optional
BaseFunctions = List[StrictInt]

# EnumDefinition
CanonicalName = StrictStr

# FunctionDefinition
Implemented = StrictBool
Virtual = StrictBool

# ContractDefinition
Abstract = StrictBool
ContractDependencies = List[StrictInt]
FullyImplemented = StrictBool
LinearizedBaseContracts = List[StrictInt]
# optional
UsedErrors = List[StrictInt]

# EventDefinition
Anonymous = StrictBool

# ModifierDefinition
BaseModifiers = List[StrictInt]

# UserDefinedTypeName
ReferencedDeclaration = StrictInt

# Return
FunctionReturnParameters = StrictInt

# VariableDeclarationStatement
Assignments = List[Optional[StrictInt]]

# Assignment
IsConstant = StrictBool
IsLValue = StrictBool
IsPure = StrictBool
LValueRequested = StrictBool

# FunctionCall
Names = List[StrictStr]
TryCall = StrictBool

# Identifier
OverloadedDeclarations = List[StrictInt]
# optional
ReferencedDeclaration = StrictInt

# Literal
HexValue = StrictStr
Value = StrictStr

# MemberAccess
MemberName = StrictStr

# TupleExpression
IsInlineArray = StrictBool

# UnaryOperation
Prefix = StrictBool

# TryCatchClause
ErrorName = StrictStr

# StructuredDocumentation
Text = StrictStr

# ImportDirective
UnitAlias = StrictStr

# YulLiteralValue
Type = StrictStr
