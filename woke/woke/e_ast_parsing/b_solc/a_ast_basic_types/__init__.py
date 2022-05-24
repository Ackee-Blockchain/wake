from typing import Dict, List, Optional, NewType

from pydantic.types import StrictBool, StrictInt, StrictStr

# Comments are the first ocurrence per the ordering in the definition file

# SolcNode
AstNodeId = NewType("AstNodeId", StrictInt)
Src = StrictStr

# SolcSourceUnit
SourceLocation = StrictStr
AbsolutePath = StrictStr
ExportedSymbols = Dict[StrictStr, List[AstNodeId]]
# optional
License = StrictStr

# SolcPragmaDirective
Literals = List[StrictStr]

# SolcImportDirective
File = StrictStr
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
BaseFunctions = List[AstNodeId]

# EnumDefinition
CanonicalName = StrictStr

# FunctionDefinition
Implemented = StrictBool
Virtual = StrictBool

# ContractDefinition
Abstract = StrictBool
ContractDependencies = List[AstNodeId]
FullyImplemented = StrictBool
LinearizedBaseContracts = List[AstNodeId]
# optional
UsedErrors = List[AstNodeId]

# EventDefinition
Anonymous = StrictBool

# ModifierDefinition
BaseModifiers = List[AstNodeId]

# UserDefinedTypeName
ReferencedDeclaration = AstNodeId

# Return
FunctionReturnParameters = AstNodeId

# VariableDeclarationStatement
Assignments = List[Optional[AstNodeId]]

# Assignment
IsConstant = StrictBool
IsLValue = StrictBool
IsPure = StrictBool
LValueRequested = StrictBool

# FunctionCall
Names = List[StrictStr]
TryCall = StrictBool

# Identifier
OverloadedDeclarations = List[AstNodeId]

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
