import enum
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, Extra

__doc__ = """Solc standard JSON output data model as described by https://docs.soliditylang.org/en/v0.8.12/using-the-compiler.html#output-description"""


def _to_camel(s: str) -> str:
    split = s.split("_")
    return split[0].lower() + "".join([w.capitalize() for w in split[1:]])


class SolcOutputModel(BaseModel):
    class Config:
        alias_generator = _to_camel
        extra = Extra.forbid


class SolcOutputErrorSourceLocation(SolcOutputModel):
    file: str
    start: int
    end: int

    def __members(self) -> Tuple:
        return self.file, self.start, self.end

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.__members() == other.__members()
        return NotImplemented

    def __hash__(self):
        return hash(self.__members())


class SolcOutputErrorSecondarySourceLocation(SolcOutputModel):
    file: str
    start: int
    end: int
    message: str

    def __members(self) -> Tuple:
        return self.file, self.start, self.end, self.message

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.__members() == other.__members()
        return NotImplemented

    def __hash__(self):
        return hash(self.__members())


class SolcOutputErrorTypeEnum(str, enum.Enum):
    """Solc output error types as described by https://docs.soliditylang.org/en/v0.8.11/using-the-compiler.html#error-types"""

    JSON_ERROR = "JSONError"
    """JSON input doesn’t conform to the required format, e.g. input is not a JSON object, the language is not supported, etc."""
    IO_ERROR = "IOError"
    """IO and import processing errors, such as unresolvable URL or hash mismatch in supplied sources."""
    PARSER_ERROR = "ParserError"
    """Source code doesn’t conform to the language rules."""
    DOCSTRING_PARSING_ERROR = "DocstringParsingError"
    """The NatSpec tags in the comment block cannot be parsed."""
    SYNTAX_ERROR = "SyntaxError"
    """Syntactical error, such as continue is used outside of a for loop."""
    DECLARATION_ERROR = "DeclarationError"
    """Invalid, unresolvable or clashing identifier names. e.g. `Identifier not found`"""
    TYPE_ERROR = "TypeError"
    """Error within the type system, such as invalid type conversions, invalid assignments, etc."""
    UNIMPLEMENTED_FEATURE_ERROR = "UnimplementedFeatureError"
    """Feature is not supported by the compiler, but is expected to be supported in future versions."""
    INTERNAL_COMPILER_ERROR = "InternalCompilerError"
    """Internal bug triggered in the compiler - this should be reported as an issue."""
    EXCEPTION = "Exception"
    """Unknown failure during compilation - this should be reported as an issue."""
    COMPILER_ERROR = "CompilerError"
    """Invalid use of the compiler stack - this should be reported as an issue."""
    FATAL_ERROR = "FatalError"
    """Fatal error not processed correctly - this should be reported as an issue."""
    WARNING = "Warning"
    """A warning, which didn’t stop the compilation, but should be addressed if possible."""
    INFO = "Info"
    """Information that the compiler thinks the user might find useful, but is not dangerous and does not necessarily need to be addressed."""


class SolcOutputErrorSeverityEnum(str, enum.Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class SolcOutputStorageLayoutTypeEncodingEnum(str, enum.Enum):
    INPLACE = "inplace"
    """Data is laid out contiguously in storage"""
    MAPPING = "mapping"
    """Keccak-256 hash-based method (see https://docs.soliditylang.org/en/latest/internals/layout_in_storage.html#mappings-and-dynamic-arrays)"""
    DYNAMIC_ARRAY = "dynamic_array"
    """Keccak-256 hash-based method (see https://docs.soliditylang.org/en/latest/internals/layout_in_storage.html#mappings-and-dynamic-arrays)"""
    BYTES = "bytes"
    """Single slot or Keccak-256 hash-based depending on the data size (see https://docs.soliditylang.org/en/latest/internals/layout_in_storage.html#bytes-and-string)"""


class SolcOutputError(SolcOutputModel):
    source_location: Optional[SolcOutputErrorSourceLocation]
    secondary_source_locations: Optional[List[SolcOutputErrorSecondarySourceLocation]]
    type: SolcOutputErrorTypeEnum
    component: str
    severity: SolcOutputErrorSeverityEnum
    error_code: Optional[str]
    message: str
    formatted_message: Optional[str]

    def __members(self) -> Tuple:
        return (
            self.source_location,
            tuple(self.secondary_source_locations)
            if self.secondary_source_locations
            else None,
            self.type,
            self.component,
            self.severity,
            self.error_code,
            self.message,
            self.formatted_message,
        )

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.__members() == other.__members()
        return NotImplemented

    def __hash__(self):
        return hash(self.__members())


class SolcOutputSourceInfo(SolcOutputModel):
    id: int
    ast: Optional[Dict]


class SolcOutputStorageLayoutStorage(SolcOutputModel):
    ast_id: int
    contract: str
    label: str
    offset: int
    slot: int
    type: str


class SolcOutputStorageLayoutType(SolcOutputModel):
    encoding: SolcOutputStorageLayoutTypeEncodingEnum
    label: str
    number_of_bytes: int
    base: Optional[str] = None
    key: Optional[str] = None
    value: Optional[str] = None
    members: Optional[List[SolcOutputStorageLayoutStorage]] = None


class SolcOutputStorageLayout(SolcOutputModel):
    storage: List[SolcOutputStorageLayoutStorage]
    types: Optional[Dict[str, SolcOutputStorageLayoutType]] = None


class SolcOutputEvmBytecodeFunctionDebugData(SolcOutputModel):
    entry_point: Optional[int]
    id: Optional[int]
    parameter_slots: int
    return_slots: int


class SolcOutputEvmBytecodeGeneratedSources(SolcOutputModel):
    ast: Dict
    contents: str
    id: int
    language: str
    name: str


class SolcOutputEvmBytecodeLinkReferencesInfo(SolcOutputModel):
    start: int
    length: int


class SolcOutputEvmBytecodeData(SolcOutputModel):
    function_debug_data: Optional[
        Dict[str, SolcOutputEvmBytecodeFunctionDebugData]
    ] = None  # internal name of the function -> debug data
    object: Optional[str] = None
    opcodes: Optional[str] = None
    source_map: Optional[str] = None
    generated_sources: Optional[List[SolcOutputEvmBytecodeGeneratedSources]] = None
    link_references: Optional[
        Dict[str, Dict[str, List[SolcOutputEvmBytecodeLinkReferencesInfo]]]
    ] = None


class SolcOutputEvmDeployedBytecodeData(SolcOutputEvmBytecodeData):
    immutable_references: Optional[
        Dict[str, List[SolcOutputEvmBytecodeLinkReferencesInfo]]
    ] = None


class SolcOutputEvmData(SolcOutputModel):
    assembly: Optional[str] = None
    legacy_assembly: Optional[Dict] = None  # TODO
    bytecode: Optional[SolcOutputEvmBytecodeData] = None
    deployed_bytecode: Optional[SolcOutputEvmDeployedBytecodeData] = None
    method_identifiers: Optional[Dict[str, str]] = None
    gas_estimates: Optional[Dict] = None  # TODO


class SolcOutputEwasmData(SolcOutputModel):
    wast: Optional[str]
    """S-expressions format"""
    wasm: Optional[str]
    """Binary format (hex string)"""


# TODO provide better data model for solc output
class SolcOutputContractInfo(SolcOutputModel):
    abi: Optional[List] = None
    """The Ethereum Contract ABI. If empty, it is represented as an empty array. See https://docs.soliditylang.org/en/latest/abi-spec.html."""
    metadata: Optional[str] = None
    """Serialized JSON metadata string. See https://docs.soliditylang.org/en/latest/metadata.html."""
    userdoc: Optional[Dict] = None
    """User documentation (natspec)"""
    devdoc: Optional[Dict] = None
    """Developer documentation (natspec)"""
    ir: Optional[str] = None
    """Intermediate representation (string)"""
    storage_layout: Optional[SolcOutputStorageLayout] = None
    """See https://docs.soliditylang.org/en/latest/internals/layout_in_storage.html#json-output"""
    evm: Optional[SolcOutputEvmData] = None
    """EVM-related outputs"""
    ewasm: Optional[SolcOutputEwasmData] = None
    """Ewasm related outputs"""


class SolcOutput(SolcOutputModel):
    errors: List[SolcOutputError] = []
    sources: Dict[str, SolcOutputSourceInfo] = {}
    contracts: Dict[
        str, Dict[str, SolcOutputContractInfo]
    ] = {}  # source_unit_name -> (contract_name -> info)
