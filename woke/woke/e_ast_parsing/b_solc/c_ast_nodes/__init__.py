from typing import TYPE_CHECKING, Any, Match, Union, List
from typing_extensions import Literal, Annotated
import re
from dataclasses import dataclass

from pydantic import Field
from pydantic.class_validators import validator

from woke.e_ast_parsing.a_abc import AstAbc
from woke.e_ast_parsing.b_solc.a_ast_basic_types import *
from woke.e_ast_parsing.b_solc.b_ast_enums import *

REGEX_SRC = re.compile(r"(\d+):(\d+):(\d+)")
PYDANTIC_CONFIG_EXTRA = "forbid"
PYDANTIC_CONFIG_ALLOW_MUTATION = False


def to_camel(s: str) -> str:
    split = s.split("_")
    return split[0].lower() + "".join([w.capitalize() for w in split[1:]])


class ConfiguredModel(AstAbc):
    class Config:
        alias_generator = to_camel
        extra = PYDANTIC_CONFIG_EXTRA
        allow_mutation = PYDANTIC_CONFIG_ALLOW_MUTATION


# probably best not to use this
# def annotate_union(typ):
#     return Annotated[typ, Field(discriminator='nodeType')]

SolcTopLevelMemberUnion = Union[
    "SolcPragmaDirective",
    "SolcImportDirective",
    # new in solc X
    "SolcVariableDeclaration",
    "SolcEnumDefinition",
    "SolcFunctionDefinition",
    "SolcStructDefinition",
    "SolcErrorDefinition",
    # new in solc 0.8.8
    "SolcUserDefinedValueTypeDefinition",
    # everywhere
    "SolcContractDefinition",
]

SolcContractMemberUnion = Union[
    "SolcEnumDefinition",
    "SolcErrorDefinition",
    "SolcEventDefinition",
    "SolcFunctionDefinition",
    "SolcModifierDefinition",
    "SolcStructDefinition",
    "SolcUserDefinedValueTypeDefinition",
    "SolcUsingForDirective",
    "SolcVariableDeclaration",
]

SolcLibraryNameUnion = Union[
    "SolcUserDefinedTypeName",
    "SolcIdentifierPath",
]

SolcTypeNameUnion = Union[
    "SolcArrayTypeName",
    "SolcElementaryTypeName",
    "SolcFunctionTypeName",
    "SolcMapping",
    "SolcUserDefinedTypeName",
]

SolcExpressionUnion = Union[
    "SolcAssignment",
    "SolcBinaryOperation",
    "SolcConditional",
    "SolcElementaryTypeNameExpression",
    "SolcFunctionCall",
    # 'SolcFunctionCallOptions',
    "SolcIdentifier",
    "SolcIndexAccess",
    "SolcIndexRangeAccess",
    "SolcLiteral",
    "SolcMemberAccess",
    "SolcNewExpression",
    # 'SolcTupleExpression',
    "SolcUnaryOperation",
]

SolcInitExprUnion = Union[
    "SolcExpressionStatement",
    "SolcVariableDeclarationStatement",
]

SolcStatementUnion = Union[
    "SolcBlock",
    "SolcBreak",
    "SolcContinue",
    "SolcDoWhileStatement",
    "SolcEmitStatement",
    "SolcExpressionStatement",
    "SolcForStatement",
    "SolcIfStatement",
    "SolcInlineAssembly",
    "SolcPlaceholderStatement",
    "SolcReturn",
    "SolcRevertStatement",
    "SolcTryStatement",
    # 'SolcUncheckedBlock',
    "SolcVariableDeclarationStatement",
    "SolcWhileStatement",
]

YulStatementUnion = Union[
    "YulAssignment",
    "YulBlock",
    "YulBreak",
    "YulContinue",
    "YulExpressionStatement",
    "YulLeave",
    "YulForLoop",
    "YulFunctionDefinition",
    "YulIf",
    "YulSwitch",
    "YulVariableDeclaration",
]

YulExpressionUnion = Union[
    "YulFunctionCall",
    "YulIdentifier",
    "YulLiteralUnion",
]

YulLiteralUnion = Union[
    "YulLiteralValue",
    "YulLiteralHexValue",
]

Declarations = List[Optional["SolcVariableDeclaration"]]

# ModifierInvocation
ModifierName = Union["SolcIdentifier", "SolcIdentifierPath"]

# InheritanceSpecifier
BaseName = Union["SolcUserDefinedTypeName", "SolcIdentifierPath"]

Overrides = Union[
    List["SolcUserDefinedTypeName"],
    List["SolcIdentifierPath"],
]

YulCaseValue = Union[
    Literal["default"],
    "YulLiteralUnion",
]

# VariableDeclaration
class TypeDescriptionsModel(ConfiguredModel):
    type_identifier: Optional[StrictStr]
    type_string: Optional[StrictStr]


class SymbolAliasModel(ConfiguredModel):  # helper class
    foreign: "SolcIdentifier"
    local: Optional[StrictStr]
    name_location: Optional[NameLocation]


# InlineAssembly
class ExternalReferenceModel(ConfiguredModel):  # helper class
    declaration: StrictInt
    is_offset: StrictBool
    is_slot: StrictBool
    src: Src
    value_size: StrictInt
    suffix: Optional[InlineAssemblySuffix]


@dataclass
class SrcParsed:
    byte_offset: int
    byte_length: int
    file_id: int


class SolcOrYulNode(ConfiguredModel):
    src: Src

    @validator("src")
    def parse_src(cls, src: Src) -> SrcParsed:
        res = re.search(REGEX_SRC, src)
        assert isinstance(res, Match), "Bad src"
        [m1, m2, m3] = [int(res.group(i)) for i in range(1, 4)]
        return SrcParsed(m1, m2, m3)


class SolcNode(SolcOrYulNode):
    id: Id


class YulNode(SolcOrYulNode):
    pass


class SolcSourceUnit(SolcNode):
    # override alias
    nodeType: Literal["SourceUnit"] = Field(alias="nodeType")
    # required
    absolute_path: AbsolutePath
    exported_symbols: ExportedSymbols
    nodes: List[Annotated[SolcTopLevelMemberUnion, Field(discriminator="nodeType")]]
    # optional
    license: Optional[License]


# todo: replace by __root__
AstSolc = SolcSourceUnit


class SolcPragmaDirective(SolcNode):
    # override alias
    nodeType: Literal["PragmaDirective"] = Field(alias="nodeType")
    literals: Literals


class SolcImportDirective(SolcNode):
    # override alias
    nodeType: Literal["ImportDirective"] = Field(alias="nodeType")
    # required
    absolute_path: AbsolutePath
    file: File
    scope: Scope
    source_unit: SourceUnit
    symbol_aliases: List[SymbolAliasModel]
    unit_alias: UnitAlias
    # optional
    name_location: Optional[NameLocation]


class SolcVariableDeclaration(SolcNode):
    # required
    # override alias
    nodeType: Literal["VariableDeclaration"] = Field(alias="nodeType")
    name: Name
    constant: Constant
    mutability: Mutability
    scope: Scope
    state_variable: StateVariable
    storage_location: StorageLocation
    type_descriptions: "TypeDescriptionsModel"
    visibility: Visibility
    # optional
    name_location: Optional[NameLocation]
    base_functions: Optional[BaseFunctions]
    documentation: Optional["SolcStructuredDocumentation"]
    function_selector: Optional[StrictStr]
    indexed: Optional[Indexed]
    overrides: Optional["SolcOverrideSpecifier"]
    type_name: Optional[SolcTypeNameUnion]
    value: Optional[SolcExpressionUnion]


class SolcEnumDefinition(SolcNode):
    # override alias
    nodeType: Literal["EnumDefinition"] = Field(alias="nodeType")
    # required
    name: Name
    canonical_name: CanonicalName
    members: List["SolcEnumValue"]
    # optional
    name_location: Optional[NameLocation]


class SolcFunctionDefinition(SolcNode):
    # override alias
    nodeType: Literal["FunctionDefinition"] = Field(alias="nodeType")
    # required
    name: Name
    implemented: Implemented
    kind: FunctionKind
    modifiers: List["SolcModifierInvocation"]
    parameters: "SolcParameterList"
    return_parameters: "SolcParameterList"
    scope: Scope
    state_mutability: StateMutability
    virtual: Virtual
    visibility: Visibility
    # optional
    name_location: Optional[NameLocation]
    base_functions: Optional[BaseFunctions]
    documentation: Optional["SolcStructuredDocumentation"]
    function_selector: Optional[FunctionSelector]
    body: Optional["SolcBlock"]
    overrides: Optional["SolcOverrideSpecifier"]


class SolcStructDefinition(SolcNode):
    # override alias
    nodeType: Literal["StructDefinition"] = Field(alias="nodeType")
    # required
    name: Name
    canonical_name: CanonicalName
    members: List["SolcVariableDeclaration"]
    scope: Scope
    visibility: Visibility
    # optional
    name_location: Optional[NameLocation]


class SolcErrorDefinition(SolcNode):
    # override alias
    nodeType: Literal["ErrorDefinition"] = Field(alias="nodeType")
    # required
    name: Name
    name_location: NameLocation
    parameters: "SolcParameterList"
    # optional
    documentation: Optional["SolcStructuredDocumentation"]


class SolcUserDefinedValueTypeDefinition(SolcNode):
    # override alias
    nodeType: Literal["UserDefinedValueTypeDefinition"] = Field(alias="nodeType")
    # required
    name: Name
    underlying_type: SolcTypeNameUnion = Field(discriminator="nodeType")
    # optional
    name_location: Optional[NameLocation]
    canonical_name: Optional[CanonicalName]


class SolcContractDefinition(SolcNode):
    # override alias
    nodeType: Literal["ContractDefinition"] = Field(alias="nodeType")
    # required
    name: Name
    abstract: Abstract
    base_contracts: List["SolcInheritanceSpecifier"]
    contract_dependencies: ContractDependencies
    contract_kind: ContractKind
    fully_implemented: FullyImplemented
    linearized_base_contracts: LinearizedBaseContracts
    nodes: List[Annotated[SolcContractMemberUnion, Field(discriminator="nodeType")]]
    scope: Scope
    # optional
    name_location: Optional[NameLocation]
    canonical_name: Optional[CanonicalName]
    documentation: Optional["SolcStructuredDocumentation"]
    used_errors: Optional[UsedErrors]


class SolcEventDefinition(SolcNode):
    # override alias
    nodeType: Literal["EventDefinition"] = Field(alias="nodeType")
    # required
    name: Name
    anonymous: Anonymous
    parameters: "SolcParameterList"
    # optional
    name_location: Optional[NameLocation]
    documentation: Optional["SolcStructuredDocumentation"]


class SolcModifierDefinition(SolcNode):
    # override alias
    nodeType: Literal["ModifierDefinition"] = Field(alias="nodeType")
    # required
    name: Name
    body: "SolcBlock"
    parameters: "SolcParameterList"
    virtual: Virtual
    visibility: Visibility
    # optional
    name_location: Optional[NameLocation]
    base_modifiers: Optional[BaseModifiers]
    documentation: Optional["SolcStructuredDocumentation"]
    overrides: Optional["SolcOverrideSpecifier"]


class SolcUsingForDirective(SolcNode):
    # override alias
    nodeType: Literal["UsingForDirective"] = Field(alias="nodeType")
    # required
    # library_name: LibraryName
    library_name: SolcLibraryNameUnion = Field(discriminator="nodeType")
    type_name: SolcTypeNameUnion = Field(discriminator="nodeType")
    # optional


class SolcArrayTypeName(SolcNode):
    # override alias
    nodeType: Literal["ArrayTypeName"] = Field(alias="nodeType")
    # required
    type_descriptions: TypeDescriptionsModel
    base_type: SolcTypeNameUnion = Field(discriminator="nodeType")
    # optional
    length: Optional[SolcExpressionUnion]


class SolcElementaryTypeName(SolcNode):
    # override alias
    nodeType: Literal["ElementaryTypeName"] = Field(alias="nodeType")
    # required
    type_descriptions: TypeDescriptionsModel
    name: Name
    # optional
    state_mutability: Optional[StateMutability]


class SolcFunctionTypeName(SolcNode):
    # override alias
    nodeType: Literal["FunctionTypeName"] = Field(alias="nodeType")
    # required
    type_descriptions: TypeDescriptionsModel
    parameter_types: "SolcParameterList"
    return_parameter_types: "SolcParameterList"
    state_mutability: StateMutability
    visibility: Visibility
    # optional


class SolcMapping(SolcNode):
    # override alias
    nodeType: Literal["Mapping"] = Field(alias="nodeType")
    # required
    type_descriptions: TypeDescriptionsModel
    key_type: SolcTypeNameUnion = Field(discriminator="nodeType")
    value_Type: SolcTypeNameUnion = Field(discriminator="nodeType")
    # optional


class SolcUserDefinedTypeName(SolcNode):
    nodeType: Literal["UserDefinedTypeName"] = Field(alias="nodeType")
    # required
    type_descriptions: TypeDescriptionsModel
    referenced_declaration: ReferencedDeclaration
    # optional
    # TODO:
    contract_scope: Optional[Scope]
    name: Optional[Name]
    path_node: Optional["SolcIdentifierPath"]


class SolcBlock(SolcNode):
    # override alias
    nodeType: Literal["Block"] = Field(alias="nodeType")
    # required
    # optional
    # TODO:
    documentation: Optional[StrictStr]
    statements: Optional[
        List[Annotated[SolcStatementUnion, Field(discriminator="nodeType")]]
    ]


class SolcBreak(SolcNode):
    # override alias
    nodeType: Literal["Break"] = Field(alias="nodeType")
    # required
    # optional
    # TODO:
    documentation: Optional[StrictStr]


class SolcContinue(SolcNode):
    # override alias
    nodeType: Literal["Continue"] = Field(alias="nodeType")
    # required
    # optional
    documentation: Optional[StrictStr]


class SolcDoWhileStatement(SolcNode):
    # override alias
    nodeType: Literal["DoWhileStatement"] = Field(alias="nodeType")
    # required
    body: SolcStatementUnion = Field(discriminator="nodeType")
    condition: SolcExpressionUnion = Field(discriminator="nodeType")
    # optional
    documentation: Optional[StrictStr]


class SolcEmitStatement(SolcNode):
    # override alias
    nodeType: Literal["EmitStatement"] = Field(alias="nodeType")
    # required
    event_call: "SolcFunctionCall"
    # optional
    documentation: Optional[StrictStr]


class SolcExpressionStatement(SolcNode):
    # override alias
    nodeType: Literal["ExpressionStatement"] = Field(alias="nodeType")
    # required
    expression: SolcExpressionUnion = Field(discriminator="nodeType")
    # optional
    documentation: Optional[StrictStr]


class SolcForStatement(SolcNode):
    # override alias
    nodeType: Literal["ForStatement"] = Field(alias="nodeType")
    # required
    body: SolcStatementUnion = Field(discriminator="nodeType")
    # optional
    documentation: Optional[StrictStr]
    condition: Optional[SolcExpressionUnion]
    initialization_expression: Optional[SolcInitExprUnion]
    loop_expression: "SolcExpressionStatement"


class SolcIfStatement(SolcNode):
    # override alias
    nodeType: Literal["IfStatement"] = Field(alias="nodeType")
    # required
    condition: SolcExpressionUnion = Field(discriminator="nodeType")
    true_body: SolcStatementUnion = Field(discriminator="nodeType")
    # optional
    documentation: Optional[StrictStr]
    false_body: Optional[SolcStatementUnion]


class SolcInlineAssembly(SolcNode):
    # override alias
    nodeType: Literal["InlineAssembly"] = Field(alias="nodeType")
    # required
    # this one requires special care...
    ast: "YulBlock" = Field(..., alias="AST")
    evm_version: InlineAssemblyEvmVersion
    external_references: List[ExternalReferenceModel]
    # optional
    documentation: Optional[StrictStr]


class SolcPlaceholderStatement(SolcNode):
    # override alias
    nodeType: Literal["PlaceholderStatement"] = Field(alias="nodeType")
    # required
    # optional
    documentation: Optional[StrictStr]


class SolcReturn(SolcNode):
    # override alias
    nodeType: Literal["Return"] = Field(alias="nodeType")
    # required
    function_return_parameters: FunctionReturnParameters
    # optional
    documentation: Optional[StrictStr]
    expression: Optional[SolcExpressionUnion]


class SolcRevertStatement(SolcNode):
    # override alias
    nodeType: Literal["RevertStatement"] = Field(alias="nodeType")
    # required
    error_call: "SolcFunctionCall"
    # optional
    documentation: Optional[StrictStr]


class SolcTryStatement(SolcNode):
    # override alias
    nodeType: Literal["TryStatement"] = Field(alias="nodeType")
    # required
    clauses: List["SolcTryCatchClause"]
    external_call: "SolcFunctionCall"
    # optional
    documentation: Optional[StrictStr]


class SolcUncheckedBlock(SolcNode):
    # override alias
    nodeType: Literal["UncheckedBlock"] = Field(alias="nodeType")
    # required
    statements: List[Annotated[SolcStatementUnion, Field(discriminator="nodeType")]]
    # optional
    documentation: Optional[StrictStr]


class SolcVariableDeclarationStatement(SolcNode):
    # override alias
    nodeType: Literal["VariableDeclarationStatement"] = Field(alias="nodeType")
    # required
    assignments: Assignments
    declarations: Declarations
    # optional
    documentation: Optional[StrictStr]
    initial_value: Optional[SolcExpressionUnion]


class SolcWhileStatement(SolcNode):
    # override alias
    nodeType: Literal["WhileStatement"] = Field(alias="nodeType")
    # required
    body: SolcStatementUnion = Field(discriminator="nodeType")
    condition: SolcExpressionUnion = Field(discriminator="nodeType")
    # optional
    documentation: Optional[StrictStr]


class SolcAssignment(SolcNode):
    # override alias
    nodeType: Literal["Assignment"] = Field(alias="nodeType")
    # required
    is_constant: IsConstant
    is_l_value: IsLValue
    is_pure: IsPure
    l_value_requested: LValueRequested
    type_descriptions: TypeDescriptionsModel
    left_hand_side: SolcExpressionUnion = Field(discriminator="nodeType")
    operator: AssignmentOperator
    right_hand_side: SolcExpressionUnion = Field(discriminator="nodeType")
    # optional
    argument_types: Optional[List[TypeDescriptionsModel]]


class SolcBinaryOperation(SolcNode):
    # override alias
    nodeType: Literal["BinaryOperation"] = Field(alias="nodeType")
    # required
    is_constant: IsConstant
    is_l_value: IsLValue
    is_pure: IsPure
    l_value_requested: LValueRequested
    type_descriptions: TypeDescriptionsModel
    common_type: TypeDescriptionsModel
    left_expression: SolcExpressionUnion = Field(discriminator="nodeType")
    operator: BinaryOpOperator
    right_expression: SolcExpressionUnion = Field(discriminator="nodeType")
    # optional
    argument_types: Optional[List[TypeDescriptionsModel]]


class SolcConditional(SolcNode):
    # override alias
    nodeType: Literal["Conditional"] = Field(alias="nodeType")
    # required
    is_constant: IsConstant
    is_l_value: IsLValue
    is_pure: IsPure
    l_value_requested: LValueRequested
    type_descriptions: TypeDescriptionsModel
    condition: SolcExpressionUnion = Field(discriminator="nodeType")
    false_expression: SolcExpressionUnion = Field(discriminator="nodeType")
    true_expression: SolcExpressionUnion = Field(discriminator="nodeType")
    # optional
    argument_types: Optional[List[TypeDescriptionsModel]]


class SolcElementaryTypeNameExpression(SolcNode):
    # override alias
    nodeType: Literal["ElementaryTypeNameExpression"] = Field(alias="nodeType")
    # required
    is_constant: IsConstant
    is_l_value: IsLValue
    is_pure: IsPure
    l_value_requested: LValueRequested
    type_descriptions: TypeDescriptionsModel
    type_name: "SolcElementaryTypeName"
    # optional
    argument_types: Optional[List[TypeDescriptionsModel]]


class SolcFunctionCall(SolcNode):
    # override alias
    nodeType: Literal["FunctionCall"] = Field(alias="nodeType")
    # required
    is_constant: IsConstant
    is_l_value: IsLValue
    is_pure: IsPure
    l_value_requested: LValueRequested
    type_descriptions: TypeDescriptionsModel
    arguments: List[Annotated[SolcExpressionUnion, Field(discriminator="nodeType")]]
    expression: SolcExpressionUnion = Field(discriminator="nodeType")
    kind: FunctionCallKind
    names: Names
    try_call: TryCall
    # optional
    argument_types: Optional[List[TypeDescriptionsModel]]


class SolcFunctionCallOptions(SolcNode):
    # override alias
    nodeType: Literal["FunctionCallOptions"] = Field(alias="nodeType")
    # required
    is_constant: IsConstant
    is_pure: IsPure
    l_value_requested: LValueRequested
    type_descriptions: TypeDescriptionsModel
    expression: SolcExpressionUnion = Field(discriminator="nodeType")
    names: Names
    options: List[Annotated[SolcExpressionUnion, Field(discriminator="nodeType")]]
    # optional
    # TODO:
    is_l_value: Optional[IsLValue]
    argument_types: Optional[List[TypeDescriptionsModel]]


class SolcIdentifier(SolcNode):
    # override alias
    nodeType: Literal["Identifier"] = Field(alias="nodeType")
    # required
    name: Name
    overloaded_declarations: OverloadedDeclarations
    type_descriptions: TypeDescriptionsModel
    # optional
    argument_types: Optional[List[TypeDescriptionsModel]]
    referenced_declaration: Optional[ReferencedDeclaration]


class SolcIndexAccess(SolcNode):
    # override alias
    nodeType: Literal["IndexAccess"] = Field(alias="nodeType")
    # required
    is_constant: IsConstant
    is_l_value: IsLValue
    is_pure: IsPure
    l_value_requested: LValueRequested
    type_descriptions: TypeDescriptionsModel
    base_expression: SolcExpressionUnion = Field(discriminator="nodeType")
    index_expression: SolcExpressionUnion = Field(discriminator="nodeType")
    # optional
    argument_types: Optional[List[TypeDescriptionsModel]]


class SolcIndexRangeAccess(SolcNode):
    # override alias
    nodeType: Literal["IndexRangeAccess"] = Field(alias="nodeType")
    # required
    is_constant: IsConstant
    is_l_value: IsLValue
    is_pure: IsPure
    l_value_requested: LValueRequested
    type_descriptions: TypeDescriptionsModel
    base_expression: SolcExpressionUnion = Field(discriminator="nodeType")
    # optional
    argument_types: Optional[List[TypeDescriptionsModel]]
    end_expression: Optional[SolcExpressionUnion]
    start_expression: Optional[SolcExpressionUnion]


class SolcLiteral(SolcNode):
    # override alias
    nodeType: Literal["Literal"] = Field(alias="nodeType")
    # required
    is_constant: IsConstant
    is_l_value: IsLValue
    is_pure: IsPure
    l_value_requested: LValueRequested
    type_descriptions: TypeDescriptionsModel
    hex_value: HexValue
    kind: LiteralKind
    # optional
    argument_types: Optional[List[TypeDescriptionsModel]]
    # TODO:
    subdenomination: Optional[Any]
    value: Optional[Value]


class SolcMemberAccess(SolcNode):
    # override alias
    nodeType: Literal["MemberAccess"] = Field(alias="nodeType")
    # required
    is_constant: IsConstant
    is_l_value: IsLValue
    is_pure: IsPure
    l_value_requested: LValueRequested
    type_descriptions: TypeDescriptionsModel
    expression: SolcExpressionUnion = Field(discriminator="nodeType")
    member_name: MemberName
    # optional
    argument_types: Optional[List[TypeDescriptionsModel]]
    referenced_declaration: Optional[ReferencedDeclaration]


class SolcNewExpression(SolcNode):
    # override alias
    nodeType: Literal["NewExpression"] = Field(alias="nodeType")
    # required
    is_constant: IsConstant
    is_pure: IsPure
    l_value_requested: LValueRequested
    type_descriptions: TypeDescriptionsModel
    type_name: SolcTypeNameUnion = Field(discriminator="nodeType")
    # optional
    argument_types: Optional[List[TypeDescriptionsModel]]
    is_l_value: Optional[IsLValue]


class SolcTupleExpression(SolcNode):
    # override alias
    nodeType: Literal["TupleExpression"] = Field(alias="nodeType")
    # required
    is_constant: IsConstant
    is_l_value: IsLValue
    is_pure: IsPure
    l_value_requested: LValueRequested
    type_descriptions: TypeDescriptionsModel
    components: List[Annotated[SolcExpressionUnion, Field(discriminator="nodeType")]]
    is_inline_array: IsInlineArray
    # optional
    argument_types: Optional[List[TypeDescriptionsModel]]


class SolcUnaryOperation(SolcNode):
    # override alias
    nodeType: Literal["UnaryOperation"] = Field(alias="nodeType")
    # required
    is_constant: IsConstant
    is_l_value: IsLValue
    is_pure: IsPure
    l_value_requested: LValueRequested
    type_descriptions: TypeDescriptionsModel
    operator: UnaryOpOperator
    prefix: Prefix
    sub_expression: SolcExpressionUnion = Field(discriminator="nodeType")
    # optional
    argument_types: Optional[List[TypeDescriptionsModel]]


class SolcOverrideSpecifier(SolcNode):
    # override alias
    nodeType: Literal["OverrideSpecifier"] = Field(alias="nodeType")
    # required
    overrides: Overrides
    # optional


class SolcIdentifierPath(SolcNode):
    nodeType: Literal["IdentifierPath"] = Field(alias="nodeType")

    # required
    name: Name
    referenced_declaration: ReferencedDeclaration
    # optional


class SolcParameterList(SolcNode):
    # override alias
    nodeType: Literal["ParameterList"] = Field(alias="nodeType")
    # required
    parameters: List["SolcVariableDeclaration"]
    # optional


class SolcTryCatchClause(SolcNode):
    # override alias
    nodeType: Literal["TryCatchClause"] = Field(alias="nodeType")
    # required
    block: "SolcBlock"
    error_name: ErrorName
    # optional
    parameters: Optional["SolcParameterList"]


class SolcStructuredDocumentation(SolcNode):
    # override alias
    nodeType: Literal["StructuredDocumentation"] = Field(alias="nodeType")
    # required
    text: Text
    # optional


class SolcEnumValue(SolcNode):
    # override alias
    nodeType: Literal["EnumValue"] = Field(alias="nodeType")
    # required
    name: Name
    # optional
    name_location: Optional[NameLocation]


class SolcInheritanceSpecifier(SolcNode):
    # override alias
    nodeType: Literal["InheritanceSpecifier"] = Field(alias="nodeType")
    # required
    base_name: BaseName
    # optional
    # arguments: Optional[List['SolcExpressionAnn']]
    arguments: Optional[
        List[Annotated[SolcExpressionUnion, Field(discriminator="nodeType")]]
    ]


class SolcModifierInvocation(SolcNode):
    # override alias
    nodeType: Literal["ModifierInvocation"] = Field(alias="nodeType")
    # required
    modifier_name: ModifierName
    # optional
    arguments: Optional[
        List[Annotated[SolcExpressionUnion, Field(discriminator="nodeType")]]
    ]
    kind: Optional[ModifierInvocationKind]


class YulAssignment(YulNode):
    # override alias
    nodeType: Literal["YulAssignment"] = Field(alias="nodeType")
    # required
    value: "YulExpressionUnion"
    variable_names: List["YulIdentifier"]
    # optional


class YulBlock(YulNode):
    # override alias
    nodeType: Literal["YulBlock"] = Field(alias="nodeType")
    # required
    statements: List["YulStatementUnion"]
    # optional


class YulBreak(YulNode):
    # override alias
    nodeType: Literal["YulBreak"] = Field(alias="nodeType")
    # required

    # optional


class YulContinue(YulNode):
    # override alias
    nodeType: Literal["YulContinue"] = Field(alias="nodeType")
    # required
    # optional


class YulExpressionStatement(YulNode):
    # override alias
    nodeType: Literal["YulExpressionStatement"] = Field(alias="nodeType")
    # required
    expression: "YulExpressionUnion"
    # optional


class YulLeave(YulNode):
    # override alias
    nodeType: Literal["YulLeave"] = Field(alias="nodeType")
    # required
    # optional


class YulForLoop(YulNode):
    # override alias
    nodeType: Literal["YulForLoop"] = Field(alias="nodeType")
    # required
    body: "YulBlock"
    condition: "YulExpressionUnion"
    post: "YulBlock"
    pre: "YulBlock"
    # optional


class YulFunctionDefinition(YulNode):
    # override alias
    nodeType: Literal["YulFunctionDefinition"] = Field(alias="nodeType")
    # required
    body: "YulBlock"
    name: Name
    parameters: List["YulTypedName"]
    return_variables: List["YulTypedName"]
    # optional


class YulIf(YulNode):
    # override alias
    nodeType: Literal["YulIf"] = Field(alias="nodeType")
    # required
    body: "YulBlock"
    condition: "YulExpressionUnion"
    # optional


class YulSwitch(YulNode):
    # override alias
    nodeType: Literal["YulSwitch"] = Field(alias="nodeType")
    # required
    cases: List["YulCase"]
    expression: "YulExpressionUnion"
    # optional


class YulVariableDeclaration(YulNode):
    # override alias
    nodeType: Literal["YulVariableDeclaration"] = Field(alias="nodeType")
    # required
    variables: List["YulTypedName"]
    # optional
    value: Optional["YulExpressionUnion"]


class YulFunctionCall(YulNode):
    # override alias
    nodeType: Literal["YulFunctionCall"] = Field(alias="nodeType")
    # required
    arguments: List["YulExpressionUnion"]
    function_name: "YulIdentifier"
    # optional


class YulIdentifier(YulNode):
    # override alias
    nodeType: Literal["YulIdentifier"] = Field(alias="nodeType")
    # required
    name: Name
    # optional


class YulLiteralValue(YulNode):
    # override alias
    nodeType: Literal["YulLiteralValue"] = Field(alias="nodeType")
    # required
    value: Value
    kind: YulLiteralValueKind
    type: Type
    # optional


class YulLiteralHexValue(YulNode):
    # override alias
    nodeType: Literal["YulLiteralHexValue"] = Field(alias="nodeType")
    # required
    hex_value: HexValue
    kind: YulLiteralHexValueKind
    type: Type
    # optional
    value: Optional[Value]


class YulTypedName(YulNode):
    # override alias
    nodeType: Literal["YulTypedName"] = Field(alias="nodeType")
    # required
    name: Name
    type: Type
    # optional


class YulCase(YulNode):
    # override alias
    nodeType: Literal["YulCase"] = Field(alias="nodeType")
    # required
    body: "YulBlock"
    # value = Annotated[YulCaseValue, Field(..., discriminator='node_type')]
    value: YulCaseValue
    # optional


# region update_forward_refs
SolcSourceUnit.update_forward_refs()
SolcPragmaDirective.update_forward_refs()
SolcImportDirective.update_forward_refs()
SolcVariableDeclaration.update_forward_refs()
SolcEnumDefinition.update_forward_refs()
SolcFunctionDefinition.update_forward_refs()
SolcStructDefinition.update_forward_refs()
SolcErrorDefinition.update_forward_refs()
SolcUserDefinedValueTypeDefinition.update_forward_refs()
SolcContractDefinition.update_forward_refs()
SolcEventDefinition.update_forward_refs()
SolcModifierDefinition.update_forward_refs()
SolcUsingForDirective.update_forward_refs()
SolcArrayTypeName.update_forward_refs()
SolcElementaryTypeName.update_forward_refs()
SolcFunctionTypeName.update_forward_refs()
SolcMapping.update_forward_refs()
SolcUserDefinedTypeName.update_forward_refs()
SolcBlock.update_forward_refs()
SolcBreak.update_forward_refs()
SolcContinue.update_forward_refs()
SolcDoWhileStatement.update_forward_refs()
SolcEmitStatement.update_forward_refs()
SolcExpressionStatement.update_forward_refs()
SolcForStatement.update_forward_refs()
SolcIfStatement.update_forward_refs()
SolcInlineAssembly.update_forward_refs()
SolcPlaceholderStatement.update_forward_refs()
SolcReturn.update_forward_refs()
SolcRevertStatement.update_forward_refs()
SolcTryStatement.update_forward_refs()
SolcUncheckedBlock.update_forward_refs()
SolcVariableDeclarationStatement.update_forward_refs()
SolcWhileStatement.update_forward_refs()
SolcAssignment.update_forward_refs()
SolcBinaryOperation.update_forward_refs()
SolcConditional.update_forward_refs()
SolcElementaryTypeNameExpression.update_forward_refs()
SolcFunctionCall.update_forward_refs()
SolcFunctionCallOptions.update_forward_refs()
SolcIdentifier.update_forward_refs()
SolcIndexAccess.update_forward_refs()
SolcIndexRangeAccess.update_forward_refs()
SolcLiteral.update_forward_refs()
SolcMemberAccess.update_forward_refs()
SolcNewExpression.update_forward_refs()
SolcTupleExpression.update_forward_refs()
SolcUnaryOperation.update_forward_refs()
SolcOverrideSpecifier.update_forward_refs()
SolcIdentifierPath.update_forward_refs()
SolcParameterList.update_forward_refs()
SolcTryCatchClause.update_forward_refs()
SolcStructuredDocumentation.update_forward_refs()
SolcEnumValue.update_forward_refs()
YulAssignment.update_forward_refs()
YulBlock.update_forward_refs()
YulBreak.update_forward_refs()
YulContinue.update_forward_refs()
YulExpressionStatement.update_forward_refs()
YulLeave.update_forward_refs()
YulForLoop.update_forward_refs()
YulFunctionDefinition.update_forward_refs()
YulIf.update_forward_refs()
YulSwitch.update_forward_refs()
YulVariableDeclaration.update_forward_refs()
YulFunctionCall.update_forward_refs()
YulIdentifier.update_forward_refs()
YulLiteralValue.update_forward_refs()
YulLiteralHexValue.update_forward_refs()
YulTypedName.update_forward_refs()
YulCase.update_forward_refs()
# endregion update_forward_refs
