import re
from typing import Any, Dict, List, Optional, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    GetCoreSchemaHandler,
    StrictBool,
    StrictInt,
    StrictStr,
    model_validator,
)
from pydantic.dataclasses import dataclass
from pydantic_core import CoreSchema, core_schema
from typing_extensions import Annotated, Literal

from .enums import *

REGEX_SRC = re.compile(r"(-?\d+):(-?\d+):(-?\d+)")


def to_camel(s: str) -> str:
    split = s.split("_")
    return split[0].lower() + "".join([w.capitalize() for w in split[1:]])


class AstModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        frozen=True,
    )


SolcTopLevelMemberUnion = Annotated[
    Union[
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
        # new in solc 0.8.13
        "SolcUsingForDirective",
        # new in solc 0.8.22
        "SolcEventDefinition",
        # everywhere
        "SolcContractDefinition",
    ],
    Field(discriminator="node_type"),
]

SolcContractMemberUnion = Annotated[
    Union[
        "SolcEnumDefinition",
        "SolcErrorDefinition",
        "SolcEventDefinition",
        "SolcFunctionDefinition",
        "SolcModifierDefinition",
        "SolcStructDefinition",
        "SolcUserDefinedValueTypeDefinition",
        "SolcUsingForDirective",
        "SolcVariableDeclaration",
    ],
    Field(discriminator="node_type"),
]

SolcLibraryNameUnion = Annotated[
    Union[
        "SolcUserDefinedTypeName",
        "SolcIdentifierPath",
    ],
    Field(discriminator="node_type"),
]

OptionalSolcLibraryNameUnion = Annotated[
    Union["SolcUserDefinedTypeName", "SolcIdentifierPath", None],
    Field(discriminator="node_type"),
]

SolcTypeNameUnion = Annotated[
    Union[
        "SolcArrayTypeName",
        "SolcElementaryTypeName",
        "SolcFunctionTypeName",
        "SolcMapping",
        "SolcUserDefinedTypeName",
    ],
    Field(discriminator="node_type"),
]

OptionalSolcTypeNameUnion = Annotated[
    Union[
        "SolcArrayTypeName",
        "SolcElementaryTypeName",
        "SolcFunctionTypeName",
        "SolcMapping",
        "SolcUserDefinedTypeName",
        None,
    ],
    Field(discriminator="node_type"),
]

SolcExpressionUnion = Annotated[
    Union[
        "SolcAssignment",
        "SolcBinaryOperation",
        "SolcConditional",
        "SolcElementaryTypeNameExpression",
        "SolcFunctionCall",
        "SolcFunctionCallOptions",
        "SolcIdentifier",
        "SolcIndexAccess",
        "SolcIndexRangeAccess",
        "SolcLiteral",
        "SolcMemberAccess",
        "SolcNewExpression",
        "SolcTupleExpression",
        "SolcUnaryOperation",
    ],
    Field(discriminator="node_type"),
]

OptionalSolcExpressionUnion = Annotated[
    Union[
        "SolcAssignment",
        "SolcBinaryOperation",
        "SolcConditional",
        "SolcElementaryTypeNameExpression",
        "SolcFunctionCall",
        "SolcFunctionCallOptions",
        "SolcIdentifier",
        "SolcIndexAccess",
        "SolcIndexRangeAccess",
        "SolcLiteral",
        "SolcMemberAccess",
        "SolcNewExpression",
        "SolcTupleExpression",
        "SolcUnaryOperation",
        None,
    ],
    Field(discriminator="node_type"),
]

SolcInitExprUnion = Annotated[
    Union[
        "SolcExpressionStatement",
        "SolcVariableDeclarationStatement",
    ],
    Field(discriminator="node_type"),
]

OptionalSolcInitExprUnion = Annotated[
    Union[
        "SolcExpressionStatement",
        "SolcVariableDeclarationStatement",
        None,
    ],
    Field(discriminator="node_type"),
]

SolcStatementUnion = Annotated[
    Union[
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
        "SolcUncheckedBlock",
        "SolcVariableDeclarationStatement",
        "SolcWhileStatement",
    ],
    Field(discriminator="node_type"),
]

OptionalSolcStatementUnion = Annotated[
    Union[
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
        "SolcUncheckedBlock",
        "SolcVariableDeclarationStatement",
        "SolcWhileStatement",
        None,
    ],
    Field(discriminator="node_type"),
]

SolcYulStatementUnion = Annotated[
    Union[
        "SolcYulAssignment",
        "SolcYulBlock",
        "SolcYulBreak",
        "SolcYulContinue",
        "SolcYulExpressionStatement",
        "SolcYulLeave",
        "SolcYulForLoop",
        "SolcYulFunctionDefinition",
        "SolcYulIf",
        "SolcYulSwitch",
        "SolcYulVariableDeclaration",
    ],
    Field(discriminator="node_type"),
]

SolcYulExpressionUnion = Annotated[
    Union[
        "SolcYulFunctionCall",
        "SolcYulIdentifier",
        "SolcYulLiteral",
    ],
    Field(discriminator="node_type"),
]

OptionalSolcYulExpressionUnion = Annotated[
    Union[
        "SolcYulFunctionCall",
        "SolcYulIdentifier",
        "SolcYulLiteral",
        None,
    ],
    Field(discriminator="node_type"),
]

# ModifierInvocation
ModifierName = Annotated[
    Union["SolcIdentifier", "SolcIdentifierPath"],
    Field(discriminator="node_type"),
]

# InheritanceSpecifier
BaseName = Annotated[
    Union["SolcUserDefinedTypeName", "SolcIdentifierPath"],
    Field(discriminator="node_type"),
]

Override = Annotated[
    Union[
        "SolcUserDefinedTypeName",
        "SolcIdentifierPath",
    ],
    Field(discriminator="node_type"),
]


class AstNodeId(int):
    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> CoreSchema:
        return core_schema.no_info_before_validator_function(cls.validate, handler(int))

    @classmethod
    def validate(cls, v):
        if not isinstance(v, int):
            raise TypeError(f"{cls.__name__} must be an int")
        return v

    def __repr__(self):
        return f"AstNodeId({int(self)})"


@dataclass
class Src:
    byte_offset: int
    byte_length: int
    file_id: int

    @model_validator(mode="before")
    def validate(cls, v):
        if isinstance(v, str):
            match = re.search(REGEX_SRC, v)
            assert (
                match
            ), f"Src must be in the format '<byte_offset>:<byte_length>:<file_id>': {v}"
            [m1, m2, m3] = [int(match.group(i)) for i in range(1, 4)]
            return {"byte_offset": m1, "byte_length": m2, "file_id": m3}
            # return Src(byte_offset=m1, byte_length=m2, file_id=m3)
        return v


class TypeDescriptionsModel(AstModel):
    type_identifier: Optional[StrictStr] = None
    type_string: Optional[StrictStr] = None


class SymbolAliasModel(AstModel):  # helper class
    foreign: "SolcIdentifier"
    local: Optional[StrictStr] = None
    name_location: Optional[Src] = None  # new in 0.8.2


# InlineAssembly
class ExternalReferenceModel(AstModel):  # helper class
    declaration: AstNodeId
    is_offset: StrictBool
    is_slot: StrictBool
    src: Src
    value_size: StrictInt
    suffix: Optional[InlineAssemblySuffix] = None


class SolcNode(AstModel):
    node_type: str
    src: Src


class SolidityNode(SolcNode):
    id: AstNodeId

    def __iter__(self):
        def iter_list(l: List):
            for item in l:
                if isinstance(item, SolidityNode):
                    yield item
                    yield from item
                elif isinstance(item, List):
                    yield from iter_list(item)

        for item in self.__dict__.values():
            if isinstance(item, SolidityNode):
                yield item
                yield from item
            elif isinstance(item, List):
                yield from iter_list(item)


class YulNode(SolcNode):
    native_src: Optional[Src] = None  # new in 0.8.21


class SolcSourceUnit(SolidityNode):
    # override alias
    node_type: Literal["SourceUnit"] = Field(alias="nodeType")
    # required
    absolute_path: StrictStr
    exported_symbols: Dict[StrictStr, List[AstNodeId]]
    nodes: List[SolcTopLevelMemberUnion]
    # optional
    license: Optional[StrictStr] = None


# todo: replace by __root__
AstSolc = SolcSourceUnit


# isConstant, isPure, isLValue was unset in <=0.7.2 when representing False (i.e. only set when True)
# see https://github.com/ethereum/solidity/commit/dd81d0555954678119d3920861645bb310f193ad


class SolcPragmaDirective(SolidityNode):
    # override alias
    node_type: Literal["PragmaDirective"] = Field(alias="nodeType")
    literals: List[StrictStr]


class SolcImportDirective(SolidityNode):
    # override alias
    node_type: Literal["ImportDirective"] = Field(alias="nodeType")
    # required
    absolute_path: StrictStr
    file: StrictStr
    scope: AstNodeId
    source_unit: AstNodeId
    symbol_aliases: List[SymbolAliasModel]
    unit_alias: StrictStr
    # optional
    name_location: Optional[Src] = None  # new in 0.8.2

    def __iter__(self):
        for symbol_alias in self.symbol_aliases:
            yield symbol_alias.foreign
            yield from symbol_alias.foreign


class SolcVariableDeclaration(SolidityNode):
    # required
    # override alias
    node_type: Literal["VariableDeclaration"] = Field(alias="nodeType")
    name: StrictStr
    constant: StrictBool
    scope: AstNodeId
    state_variable: StrictBool
    storage_location: DataLocation
    type_descriptions: "TypeDescriptionsModel"
    visibility: Visibility
    # optional
    name_location: Optional[Src] = None  # new in 0.8.2
    # immutable is new in 0.6.5 but `mutability` field is set in >=0.6.6
    # in 0.6.5 `mutability` field is not exported for immutable variables because of a bug
    # constant variables were distinguished by `constant` field in versions <= 0.6.5 (this field is still present in newer versions)
    mutability: Optional[Mutability] = None
    base_functions: Optional[List[AstNodeId]] = None
    documentation: Optional[
        "SolcStructuredDocumentation"
    ] = None  # added in 0.6.9 for state variables
    function_selector: Optional[StrictStr] = None
    indexed: Optional[StrictBool] = None
    overrides: Optional["SolcOverrideSpecifier"] = None
    type_name: OptionalSolcTypeNameUnion = (
        None  # is None only for <0.5.0 where `var` keyword was supported
    )
    value: OptionalSolcExpressionUnion = None


class SolcEnumDefinition(SolidityNode):
    # override alias
    node_type: Literal["EnumDefinition"] = Field(alias="nodeType")
    # required
    name: StrictStr
    canonical_name: StrictStr
    members: List["SolcEnumValue"]
    # optional
    name_location: Optional[Src] = None  # new in 0.8.2
    documentation: Optional["SolcStructuredDocumentation"] = None  # new in 0.8.20


class SolcFunctionDefinition(SolidityNode):
    # override alias
    node_type: Literal["FunctionDefinition"] = Field(alias="nodeType")
    # required
    name: StrictStr
    implemented: StrictBool
    kind: FunctionKind
    modifiers: List["SolcModifierInvocation"]
    parameters: "SolcParameterList"
    return_parameters: "SolcParameterList"
    scope: AstNodeId
    state_mutability: StateMutability
    virtual: StrictBool
    visibility: Visibility
    # optional
    name_location: Optional[Src] = None  # new in 0.8.2
    base_functions: Optional[List[AstNodeId]] = None
    documentation: Union["SolcStructuredDocumentation", str, None] = None
    function_selector: Optional[StrictStr] = None
    body: Optional["SolcBlock"] = None
    overrides: Optional["SolcOverrideSpecifier"] = None


class SolcStructDefinition(SolidityNode):
    # override alias
    node_type: Literal["StructDefinition"] = Field(alias="nodeType")
    # required
    name: StrictStr
    canonical_name: StrictStr
    members: List["SolcVariableDeclaration"]
    scope: AstNodeId
    visibility: Visibility
    # optional
    name_location: Optional[Src] = None  # new in 0.8.2
    documentation: Optional["SolcStructuredDocumentation"] = None  # new in 0.8.20


# new in 0.8.4
class SolcErrorDefinition(SolidityNode):
    # override alias
    node_type: Literal["ErrorDefinition"] = Field(alias="nodeType")
    # required
    name: StrictStr
    name_location: Src
    parameters: "SolcParameterList"
    # optional
    documentation: Optional["SolcStructuredDocumentation"] = None
    error_selector: Optional[StrictStr] = None


# new in 0.8.0
class SolcUserDefinedValueTypeDefinition(SolidityNode):
    # override alias
    node_type: Literal["UserDefinedValueTypeDefinition"] = Field(alias="nodeType")
    # required
    name: StrictStr
    underlying_type: "SolcElementaryTypeName"
    # optional
    name_location: Optional[Src] = None  # new in 0.8.2
    canonical_name: Optional[
        StrictStr
    ] = None  # should be present but because of a bug it is exported in >=0.8.9


class SolcContractDefinition(SolidityNode):
    # override alias
    node_type: Literal["ContractDefinition"] = Field(alias="nodeType")
    # required
    name: StrictStr
    abstract: StrictBool
    base_contracts: List["SolcInheritanceSpecifier"]
    contract_dependencies: List[AstNodeId]
    contract_kind: ContractKind
    linearized_base_contracts: List[AstNodeId]
    nodes: List[SolcContractMemberUnion]
    scope: AstNodeId
    # optional
    name_location: Optional[Src] = None  # new in 0.8.2
    canonical_name: Optional[
        StrictStr
    ] = None  # should be present but because of a bug it is exported in >=0.8.9
    fully_implemented: Optional[
        StrictBool
    ] = None  # missing when a file that imports the contract cannot be compiled
    documentation: Union["SolcStructuredDocumentation", str, None] = None
    used_errors: Optional[List[AstNodeId]] = None  # new in 0.8.4
    used_events: Optional[List[AstNodeId]] = None  # new in 0.8.20
    internal_function_ids: Optional[Dict[int, StrictInt]] = Field(
        None, alias="internalFunctionIDs"
    )


class SolcEventDefinition(SolidityNode):
    # override alias
    node_type: Literal["EventDefinition"] = Field(alias="nodeType")
    # required
    name: StrictStr
    anonymous: StrictBool
    parameters: "SolcParameterList"
    # optional
    name_location: Optional[Src] = None  # new in 0.8.2
    documentation: Optional[Union["SolcStructuredDocumentation", str]] = None
    event_selector: Optional[
        StrictStr
    ] = None  # an example: "0d3648bd0f6ba80134a33ba9275ac585d9d315f0ad8355cddefde31afa28d0e9"


class SolcModifierDefinition(SolidityNode):
    # override alias
    node_type: Literal["ModifierDefinition"] = Field(alias="nodeType")
    # required
    name: StrictStr
    parameters: "SolcParameterList"
    virtual: StrictBool
    visibility: Visibility
    # optional
    body: Optional["SolcBlock"] = None
    name_location: Optional[Src] = None  # new in 0.8.2
    base_modifiers: Optional[List[AstNodeId]] = None
    documentation: Optional[Union["SolcStructuredDocumentation", str]] = None
    overrides: Optional["SolcOverrideSpecifier"] = None


class UsingForDirectiveFunction(AstModel):
    function: Optional["SolcIdentifierPath"] = None
    definition: Optional["SolcIdentifierPath"] = None  # added in 0.8.19
    operator: Optional[
        Union[UnaryOpOperator, BinaryOpOperator]
    ] = None  # added in 0.8.19


class SolcUsingForDirective(SolidityNode):
    # override alias
    node_type: Literal["UsingForDirective"] = Field(alias="nodeType")
    # required
    # optional
    function_list: Optional[List[UsingForDirectiveFunction]] = None
    library_name: OptionalSolcLibraryNameUnion = None
    type_name: OptionalSolcTypeNameUnion = None
    global_: Optional[StrictBool] = Field(None, alias="global")

    def __iter__(self):
        if self.function_list is not None:
            for function in self.function_list:
                if function.function is not None:
                    yield function.function
                    yield from function.function
                if function.definition is not None:
                    yield function.definition
                    yield from function.definition
        if self.library_name is not None:
            yield self.library_name
            yield from self.library_name
        if self.type_name is not None:
            yield self.type_name
            yield from self.type_name


class SolcArrayTypeName(SolidityNode):
    # override alias
    node_type: Literal["ArrayTypeName"] = Field(alias="nodeType")
    # required
    type_descriptions: TypeDescriptionsModel
    base_type: SolcTypeNameUnion
    # optional
    length: OptionalSolcExpressionUnion = None


class SolcElementaryTypeName(SolidityNode):
    # override alias
    node_type: Literal["ElementaryTypeName"] = Field(alias="nodeType")
    # required
    type_descriptions: TypeDescriptionsModel
    name: StrictStr
    # optional
    state_mutability: Optional[StateMutability] = None


class SolcFunctionTypeName(SolidityNode):
    # override alias
    node_type: Literal["FunctionTypeName"] = Field(alias="nodeType")
    # required
    type_descriptions: TypeDescriptionsModel
    parameter_types: "SolcParameterList"
    return_parameter_types: "SolcParameterList"
    state_mutability: StateMutability
    visibility: Visibility
    # optional


class SolcMapping(SolidityNode):
    # override alias
    node_type: Literal["Mapping"] = Field(alias="nodeType")
    # required
    type_descriptions: TypeDescriptionsModel
    key_type: SolcTypeNameUnion
    value_type: SolcTypeNameUnion
    # optional
    key_name: Optional[StrictStr] = None  # new in 0.8.18
    key_name_location: Optional[Src] = None  # new in 0.8.18
    value_name: Optional[StrictStr] = None  # new in 0.8.18
    value_name_location: Optional[Src] = None  # new in 0.8.18


class SolcUserDefinedTypeName(SolidityNode):
    node_type: Literal["UserDefinedTypeName"] = Field(alias="nodeType")
    # required
    type_descriptions: TypeDescriptionsModel
    referenced_declaration: AstNodeId
    # optional
    contract_scope: Optional[AstNodeId] = None  # removed in 0.8.0
    name: Optional[StrictStr] = None  # removed in 0.8.0 in favor of path_node
    path_node: Optional["SolcIdentifierPath"] = None  # added in 0.8.0


class SolcBlock(SolidityNode):
    # override alias
    node_type: Literal["Block"] = Field(alias="nodeType")
    statements: List[SolcStatementUnion]
    # required
    # optional
    documentation: Optional[StrictStr] = None


class SolcBreak(SolidityNode):
    # override alias
    node_type: Literal["Break"] = Field(alias="nodeType")
    # required
    # optional
    documentation: Optional[StrictStr] = None


class SolcContinue(SolidityNode):
    # override alias
    node_type: Literal["Continue"] = Field(alias="nodeType")
    # required
    # optional
    documentation: Optional[StrictStr] = None


class SolcDoWhileStatement(SolidityNode):
    # override alias
    node_type: Literal["DoWhileStatement"] = Field(alias="nodeType")
    # required
    body: SolcStatementUnion
    condition: SolcExpressionUnion
    # optional
    documentation: Optional[StrictStr] = None


class SolcEmitStatement(SolidityNode):
    # override alias
    node_type: Literal["EmitStatement"] = Field(alias="nodeType")
    # required
    event_call: "SolcFunctionCall"
    # optional
    documentation: Optional[StrictStr] = None


class SolcExpressionStatement(SolidityNode):
    # override alias
    node_type: Literal["ExpressionStatement"] = Field(alias="nodeType")
    # required
    expression: SolcExpressionUnion
    # optional
    documentation: Optional[StrictStr] = None


class SolcForStatement(SolidityNode):
    # override alias
    node_type: Literal["ForStatement"] = Field(alias="nodeType")
    # required
    body: SolcStatementUnion
    # optional
    documentation: Optional[StrictStr] = None
    condition: OptionalSolcExpressionUnion = None
    initialization_expression: OptionalSolcInitExprUnion = None
    loop_expression: Optional[SolcExpressionStatement] = None
    is_simple_counter_loop: Optional[bool] = None  # new in 0.8.22


class SolcIfStatement(SolidityNode):
    # override alias
    node_type: Literal["IfStatement"] = Field(alias="nodeType")
    # required
    condition: SolcExpressionUnion
    true_body: SolcStatementUnion
    # optional
    documentation: Optional[StrictStr] = None
    false_body: OptionalSolcStatementUnion = None


class SolcInlineAssembly(SolidityNode):
    # override alias
    node_type: Literal["InlineAssembly"] = Field(alias="nodeType")
    # required
    # this one requires special care...
    ast: "SolcYulBlock" = Field(..., alias="AST")
    evm_version: InlineAssemblyEvmVersion
    external_references: List[ExternalReferenceModel]
    # optional
    documentation: Optional[StrictStr] = None
    flags: Optional[List[InlineAssemblyFlag]] = None


class SolcPlaceholderStatement(SolidityNode):
    # override alias
    node_type: Literal["PlaceholderStatement"] = Field(alias="nodeType")
    # required
    # optional
    documentation: Optional[StrictStr] = None


class SolcReturn(SolidityNode):
    # override alias
    node_type: Literal["Return"] = Field(alias="nodeType")
    # required
    # optional
    function_return_parameters: Optional[AstNodeId] = None
    documentation: Optional[StrictStr] = None
    expression: OptionalSolcExpressionUnion = None


class SolcRevertStatement(SolidityNode):
    # override alias
    node_type: Literal["RevertStatement"] = Field(alias="nodeType")
    # required
    error_call: "SolcFunctionCall"
    # optional
    documentation: Optional[StrictStr] = None


class SolcTryStatement(SolidityNode):
    # override alias
    node_type: Literal["TryStatement"] = Field(alias="nodeType")
    # required
    clauses: List["SolcTryCatchClause"]
    external_call: "SolcFunctionCall"
    # optional
    documentation: Optional[StrictStr] = None


# new in 0.8.0
class SolcUncheckedBlock(SolidityNode):
    # override alias
    node_type: Literal["UncheckedBlock"] = Field(alias="nodeType")
    # required
    statements: List[SolcStatementUnion]
    # optional
    documentation: Optional[StrictStr] = None


class SolcVariableDeclarationStatement(SolidityNode):
    # override alias
    node_type: Literal["VariableDeclarationStatement"] = Field(alias="nodeType")
    # required
    assignments: List[Optional[AstNodeId]] = None
    declarations: List[Optional["SolcVariableDeclaration"]] = None
    # optional
    documentation: Optional[StrictStr] = None
    initial_value: OptionalSolcExpressionUnion = None


class SolcWhileStatement(SolidityNode):
    # override alias
    node_type: Literal["WhileStatement"] = Field(alias="nodeType")
    # required
    body: SolcStatementUnion
    condition: SolcExpressionUnion
    # optional
    documentation: Optional[StrictStr] = None


class SolcAssignment(SolidityNode):
    # override alias
    node_type: Literal["Assignment"] = Field(alias="nodeType")
    # required
    is_constant: StrictBool = False
    is_l_value: StrictBool = False
    is_pure: StrictBool = False
    l_value_requested: StrictBool
    type_descriptions: TypeDescriptionsModel
    left_hand_side: SolcExpressionUnion
    operator: AssignmentOperator
    right_hand_side: SolcExpressionUnion
    # optional
    argument_types: Optional[List[TypeDescriptionsModel]] = None


class SolcBinaryOperation(SolidityNode):
    # override alias
    node_type: Literal["BinaryOperation"] = Field(alias="nodeType")
    # required
    is_constant: StrictBool = False
    is_l_value: StrictBool = False
    is_pure: StrictBool = False
    l_value_requested: StrictBool
    type_descriptions: TypeDescriptionsModel
    common_type: TypeDescriptionsModel
    left_expression: SolcExpressionUnion
    operator: BinaryOpOperator
    right_expression: SolcExpressionUnion
    # optional
    argument_types: Optional[List[TypeDescriptionsModel]] = None
    function: Optional[AstNodeId] = None  # added in 0.8.19


class SolcConditional(SolidityNode):
    # override alias
    node_type: Literal["Conditional"] = Field(alias="nodeType")
    # required
    is_constant: StrictBool = False
    is_l_value: StrictBool = False
    is_pure: StrictBool = False
    l_value_requested: StrictBool
    type_descriptions: TypeDescriptionsModel
    condition: SolcExpressionUnion
    false_expression: SolcExpressionUnion
    true_expression: SolcExpressionUnion
    # optional
    argument_types: Optional[List[TypeDescriptionsModel]] = None


class SolcElementaryTypeNameExpression(SolidityNode):
    # override alias
    node_type: Literal["ElementaryTypeNameExpression"] = Field(alias="nodeType")
    # required
    is_constant: StrictBool = False
    is_l_value: StrictBool = False
    is_pure: StrictBool = False
    l_value_requested: StrictBool
    type_descriptions: TypeDescriptionsModel
    type_name: "SolcElementaryTypeName"  # in versions < 0.6.0 this was a string
    # optional
    argument_types: Optional[List[TypeDescriptionsModel]] = None


class SolcFunctionCall(SolidityNode):
    # override alias
    node_type: Literal["FunctionCall"] = Field(alias="nodeType")
    # required
    is_constant: StrictBool = False
    is_l_value: StrictBool = False
    is_pure: StrictBool = False
    l_value_requested: StrictBool
    type_descriptions: TypeDescriptionsModel
    arguments: List[SolcExpressionUnion]
    expression: SolcExpressionUnion
    kind: FunctionCallKind
    names: List[StrictStr]
    try_call: StrictBool
    # optional
    argument_types: Optional[List[TypeDescriptionsModel]] = None
    name_locations: Optional[List[Src]] = None  # added in 0.8.16


class SolcFunctionCallOptions(SolidityNode):
    # override alias
    node_type: Literal["FunctionCallOptions"] = Field(alias="nodeType")
    # required
    is_constant: StrictBool = False
    is_l_value: StrictBool = False
    is_pure: StrictBool = False
    l_value_requested: StrictBool
    type_descriptions: TypeDescriptionsModel
    expression: SolcExpressionUnion
    names: List[StrictStr]
    options: List[SolcExpressionUnion]
    # optional
    # TODO:
    argument_types: Optional[List[TypeDescriptionsModel]] = None


class SolcIdentifier(SolidityNode):
    # override alias
    node_type: Literal["Identifier"] = Field(alias="nodeType")
    # required
    name: StrictStr
    overloaded_declarations: List[AstNodeId]
    type_descriptions: TypeDescriptionsModel
    # optional
    argument_types: Optional[List[TypeDescriptionsModel]] = None
    referenced_declaration: Optional[AstNodeId] = None


class SolcIndexAccess(SolidityNode):
    # override alias
    node_type: Literal["IndexAccess"] = Field(alias="nodeType")
    # required
    is_constant: StrictBool = False
    is_l_value: StrictBool = False
    is_pure: StrictBool = False
    l_value_requested: StrictBool
    type_descriptions: TypeDescriptionsModel
    base_expression: SolcExpressionUnion
    # optional
    argument_types: Optional[List[TypeDescriptionsModel]] = None
    index_expression: OptionalSolcExpressionUnion = None  # example when this can be None: `abi.decode(params, (address[], uint256))`


class SolcIndexRangeAccess(SolidityNode):
    # override alias
    node_type: Literal["IndexRangeAccess"] = Field(alias="nodeType")
    # required
    is_constant: StrictBool = False
    is_l_value: StrictBool = False
    is_pure: StrictBool = False
    l_value_requested: StrictBool
    type_descriptions: TypeDescriptionsModel
    base_expression: SolcExpressionUnion
    # optional
    argument_types: Optional[List[TypeDescriptionsModel]] = None
    end_expression: OptionalSolcExpressionUnion = None
    start_expression: OptionalSolcExpressionUnion = None


class SolcLiteral(SolidityNode):
    # override alias
    node_type: Literal["Literal"] = Field(alias="nodeType")
    # required
    is_constant: StrictBool = False
    is_l_value: StrictBool = False
    is_pure: StrictBool = False
    l_value_requested: StrictBool
    type_descriptions: TypeDescriptionsModel
    hex_value: StrictStr
    kind: LiteralKind  # hexString new in 0.7.0, prior to 0.7.0 hex strings were marked as strings
    # optional
    argument_types: Optional[List[TypeDescriptionsModel]] = None
    subdenomination: Optional[StrictStr] = None  # can be for example "days" or "ether"
    value: Optional[StrictStr] = None


class SolcMemberAccess(SolidityNode):
    # override alias
    node_type: Literal["MemberAccess"] = Field(alias="nodeType")
    # required
    is_constant: StrictBool = False
    is_l_value: StrictBool = False
    is_pure: StrictBool = False
    l_value_requested: StrictBool
    type_descriptions: TypeDescriptionsModel
    expression: SolcExpressionUnion
    member_name: StrictStr
    # optional
    argument_types: Optional[List[TypeDescriptionsModel]] = None
    referenced_declaration: Optional[
        AstNodeId
    ] = None  # because of a bug this is None for enum value access in versions prior to 0.8.2
    member_location: Optional[Src] = None  # added in 0.8.16


class SolcNewExpression(SolidityNode):
    # override alias
    node_type: Literal["NewExpression"] = Field(alias="nodeType")
    # required
    is_constant: StrictBool = False
    is_l_value: StrictBool = False
    is_pure: StrictBool = False
    l_value_requested: StrictBool
    type_descriptions: TypeDescriptionsModel
    type_name: SolcTypeNameUnion
    # optional
    argument_types: Optional[List[TypeDescriptionsModel]] = None


class SolcTupleExpression(SolidityNode):
    # override alias
    node_type: Literal["TupleExpression"] = Field(alias="nodeType")
    # required
    is_constant: StrictBool = False
    is_l_value: StrictBool = False
    is_pure: StrictBool = False
    l_value_requested: StrictBool
    type_descriptions: TypeDescriptionsModel
    components: List[OptionalSolcExpressionUnion] = None
    is_inline_array: StrictBool
    # optional
    argument_types: Optional[List[TypeDescriptionsModel]] = None


class SolcUnaryOperation(SolidityNode):
    # override alias
    node_type: Literal["UnaryOperation"] = Field(alias="nodeType")
    # required
    is_constant: StrictBool = False
    is_l_value: StrictBool = False
    is_pure: StrictBool = False
    l_value_requested: StrictBool
    type_descriptions: TypeDescriptionsModel
    operator: UnaryOpOperator
    prefix: StrictBool
    sub_expression: SolcExpressionUnion
    # optional
    argument_types: Optional[List[TypeDescriptionsModel]] = None
    function: Optional[AstNodeId] = None  # added in 0.8.19


class SolcOverrideSpecifier(SolidityNode):
    # override alias
    node_type: Literal["OverrideSpecifier"] = Field(alias="nodeType")
    # required
    overrides: List[Override]
    # optional


# new in 0.8.0 to replace SolcUserDefinedTypeName in many places
class SolcIdentifierPath(SolidityNode):
    node_type: Literal["IdentifierPath"] = Field(alias="nodeType")
    # required
    name: StrictStr
    referenced_declaration: AstNodeId
    # optional
    name_locations: Optional[List[Src]] = None  # added in 0.8.16


class SolcParameterList(SolidityNode):
    # override alias
    node_type: Literal["ParameterList"] = Field(alias="nodeType")
    # required
    parameters: List["SolcVariableDeclaration"]
    # optional


class SolcTryCatchClause(SolidityNode):
    # override alias
    node_type: Literal["TryCatchClause"] = Field(alias="nodeType")
    # required
    block: "SolcBlock"
    error_name: StrictStr
    # optional
    parameters: Optional["SolcParameterList"] = None


class SolcStructuredDocumentation(SolidityNode):
    # override alias
    node_type: Literal["StructuredDocumentation"] = Field(alias="nodeType")
    # required
    text: StrictStr
    # optional


class SolcEnumValue(SolidityNode):
    # override alias
    node_type: Literal["EnumValue"] = Field(alias="nodeType")
    # required
    name: StrictStr
    # optional
    name_location: Optional[Src] = None  # new in 0.8.2


class SolcInheritanceSpecifier(SolidityNode):
    # override alias
    node_type: Literal["InheritanceSpecifier"] = Field(alias="nodeType")
    # required
    base_name: BaseName
    # optional
    arguments: Optional[List[SolcExpressionUnion]] = None


class SolcModifierInvocation(SolidityNode):
    # override alias
    node_type: Literal["ModifierInvocation"] = Field(alias="nodeType")
    # required
    modifier_name: ModifierName
    # optional
    arguments: Optional[List[SolcExpressionUnion]] = None
    kind: Optional[
        ModifierInvocationKind
    ] = None  # new in 0.8.3, fixed in 0.8.4 for base constructor calls


class SolcYulAssignment(YulNode):
    # override alias
    node_type: Literal["YulAssignment"] = Field(alias="nodeType")
    # required
    value: "SolcYulExpressionUnion"
    variable_names: List["SolcYulIdentifier"]
    # optional


class SolcYulBlock(YulNode):
    # override alias
    node_type: Literal["YulBlock"] = Field(alias="nodeType")
    # required
    statements: List["SolcYulStatementUnion"]
    # optional


class SolcYulBreak(YulNode):
    # override alias
    node_type: Literal["YulBreak"] = Field(alias="nodeType")
    # required
    # optional


class SolcYulContinue(YulNode):
    # override alias
    node_type: Literal["YulContinue"] = Field(alias="nodeType")
    # required
    # optional


class SolcYulExpressionStatement(YulNode):
    # override alias
    node_type: Literal["YulExpressionStatement"] = Field(alias="nodeType")
    # required
    expression: "SolcYulExpressionUnion"
    # optional


class SolcYulLeave(YulNode):
    # override alias
    node_type: Literal["YulLeave"] = Field(alias="nodeType")
    # required
    # optional


class SolcYulForLoop(YulNode):
    # override alias
    node_type: Literal["YulForLoop"] = Field(alias="nodeType")
    # required
    body: "SolcYulBlock"
    condition: "SolcYulExpressionUnion"
    post: "SolcYulBlock"
    pre: "SolcYulBlock"
    # optional


class SolcYulFunctionDefinition(YulNode):
    # override alias
    node_type: Literal["YulFunctionDefinition"] = Field(alias="nodeType")
    # required
    body: "SolcYulBlock"
    name: StrictStr
    # optional
    parameters: Optional[List["SolcYulTypedName"]] = None
    return_variables: Optional[List["SolcYulTypedName"]] = None


class SolcYulIf(YulNode):
    # override alias
    node_type: Literal["YulIf"] = Field(alias="nodeType")
    # required
    body: "SolcYulBlock"
    condition: "SolcYulExpressionUnion"
    # optional


class SolcYulSwitch(YulNode):
    # override alias
    node_type: Literal["YulSwitch"] = Field(alias="nodeType")
    # required
    cases: List["SolcYulCase"]
    expression: "SolcYulExpressionUnion"
    # optional


class SolcYulVariableDeclaration(YulNode):
    # override alias
    node_type: Literal["YulVariableDeclaration"] = Field(alias="nodeType")
    # required
    variables: List["SolcYulTypedName"]
    # optional
    value: OptionalSolcYulExpressionUnion = None


class SolcYulFunctionCall(YulNode):
    # override alias
    node_type: Literal["YulFunctionCall"] = Field(alias="nodeType")
    # required
    arguments: List[SolcYulExpressionUnion]
    function_name: "SolcYulIdentifier"
    # optional


class SolcYulIdentifier(YulNode):
    # override alias
    node_type: Literal["YulIdentifier"] = Field(alias="nodeType")
    # required
    name: StrictStr
    # optional


class SolcYulLiteral(YulNode):
    # override alias
    node_type: Literal["YulLiteral"] = Field(alias="nodeType")
    # required
    kind: YulLiteralKind
    type: StrictStr
    # at least one of these should be set
    value: Optional[StrictStr] = None
    hex_value: Optional[StrictStr] = None  # sice 0.8.5

    @model_validator(mode="after")
    def value_or_hex_value_set(cls, value: "SolcYulLiteral"):
        assert (
            value.value is not None or value.hex_value is not None
        ), "YulLiteral: either 'value' or 'hex_value' must be set"
        return value


class SolcYulTypedName(YulNode):
    # override alias
    node_type: Literal["YulTypedName"] = Field(alias="nodeType")
    # required
    name: StrictStr
    type: StrictStr
    # optional


class SolcYulCase(YulNode):
    # override alias
    node_type: Literal["YulCase"] = Field(alias="nodeType")
    # required
    body: "SolcYulBlock"
    value: Union[Literal["default"], SolcYulLiteral]
    # optional
