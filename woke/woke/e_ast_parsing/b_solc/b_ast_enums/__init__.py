from enum import auto
from strenum import StrEnum

# Contracts
class ContractKind(StrEnum):
    CONTRACT = "contract"
    INTERFACE = "interface"
    LIBRARY = "library"


# State variables
class Mutability(StrEnum):
    MUTABLE = "mutable"
    IMMUTABLE = "immutable"
    CONSTANT = "constant"


# Functions
class FunctionKind(StrEnum):
    FUNCTION = "function"
    RECEIVE = "receive"
    CONSTRUCTOR = "constructor"
    FALLBACK = "fallback"
    FREE_FUNCTION = "freeFunction"


class Visibility(StrEnum):
    EXTERNAL = "external"
    PUBLIC = "public"
    INTERNAL = "internal"
    PRIVATE = "private"


class StateMutability(StrEnum):
    PAYABLE = "payable"
    PURE = "pure"
    NONPAYABLE = "nonpayable"
    VIEW = "view"


class ModifierInvocationKind(StrEnum):
    MODIFIER_INVOCATION = "modifierInvocation"
    BASE_CONSTRUCTOR_SPECIFIER = "baseConstructorSpecifier"


# Literals
class LiteralKind(StrEnum):
    BOOL = "bool"
    NUMBER = "number"
    STRING = "string"
    HEX_STRING = "hexString"
    UNICODE_STRING = "unicodeString"


class YulLiteralValueKind(StrEnum):
    NUMBER = "number"
    STRING = "string"
    BOOL = "bool"


class YulLiteralHexValueKind(StrEnum):
    NUMBER = "number"
    STRING = "string"
    BOOL = "bool"


# Function call
class FunctionCallKind(StrEnum):
    FUNCTION_CALL = "functionCall"
    TYPE_CONVERSION = "typeConversion"
    STRUCT_CONSTRUCTOR_CALL = "structConstructorCall"


# Compound types
class StorageLocation(StrEnum):
    CALLDATA = "calldata"
    DEFAULT = "default"
    MEMORY = "memory"
    STORAGE = "storage"


# Operations
class UnaryOpOperator(StrEnum):
    PLUS_PLUS = r"++"
    MINUS_MINUS = r"--"
    MINUS = r"-"
    NOT = r"!"
    TILDE = r"~"
    DELETE = "delete"


class AssignmentOperator(StrEnum):
    EQUALS = r"="
    PLUS_EQUALS = r"+="
    MINUS_EQUALS = r"-="
    TIMES_EQUALS = r"*="
    DIVIDE_EQUALS = r"/="
    MODULO_EQUALS = r"%="
    OR_EQUALS = r"|="
    AND_EQUALS = r"&="
    XOR_EQUALS = r"^="
    RIGHT_SHIFT_EQUALS = r">>="
    LEFT_SHIFT_EQUALS = r"<<="


class BinaryOpOperator(StrEnum):
    PLUS = r"+"
    MINUS = r"-"
    TIMES = r"*"
    DIVIDE = r"/"
    MODULO = r"%"
    EXP = r"**"
    BOOLEAN_AND = r"&&"
    BOOLEAN_OR = r"||"
    NEQ = r"!="
    EQ = r"=="
    LT = r"<"
    LTE = r"<="
    GT = r">"
    GTE = r">="
    XOR = r"^"
    BITWISE_AND = r"&"
    BITWISE_OR = r"|"
    LEFT_SHIFT = r"<<"
    RIGHT_SHIFT = r">>"


# Inline assembly
class InlineAssemblyEvmVersion(StrEnum):
    HOMESTEAD = "homestead"
    TANGERINE_WHISTLE = "tangerineWhistle"
    SPURIOUS_DRAGON = "spuriousDragon"
    BYZANTIUM = "byzantium"
    CONSTANTINOPLE = "constantinople"
    PETERSBURG = "petersburg"
    ISTANBUL = "istanbul"
    BERLIN = "berlin"
    LONDON = "london"


class InlineAssemblySuffix(StrEnum):
    SLOT = "slot"
    OFFSET = "offset"
