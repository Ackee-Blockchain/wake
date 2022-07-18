import enum


class GlobalSymbolsEnum(enum.IntEnum):
    ABI = -1
    ADDMOD = -2
    ASSERT = -3
    BLOCK = -4
    BLOCKHASH = -5
    ECRECOVER = -6
    GASLEFT = -7
    KECCAK256 = -8
    MSG = -15
    MULMOD = -16
    NOW = -17
    REQUIRE = -18
    REVERT = -19
    RIPEMD160 = -20
    SELFDESTRUCT = -21
    SHA256 = -22
    SHA3 = -23
    SUICIDE = -24
    SUPER = -25
    TX = -26
    TYPE = -27
    THIS = -28


# Contracts
class ContractKind(str, enum.Enum):
    CONTRACT = "contract"
    INTERFACE = "interface"
    LIBRARY = "library"


# State variables
class Mutability(str, enum.Enum):
    MUTABLE = "mutable"
    IMMUTABLE = "immutable"
    CONSTANT = "constant"


# Functions
class FunctionKind(str, enum.Enum):
    FUNCTION = "function"
    RECEIVE = "receive"
    CONSTRUCTOR = "constructor"
    FALLBACK = "fallback"
    FREE_FUNCTION = "freeFunction"


class Visibility(str, enum.Enum):
    EXTERNAL = "external"
    PUBLIC = "public"
    INTERNAL = "internal"
    PRIVATE = "private"


class StateMutability(str, enum.Enum):
    PAYABLE = "payable"
    PURE = "pure"
    NONPAYABLE = "nonpayable"
    VIEW = "view"


class ModifierInvocationKind(str, enum.Enum):
    MODIFIER_INVOCATION = "modifierInvocation"
    BASE_CONSTRUCTOR_SPECIFIER = "baseConstructorSpecifier"


# Literals
class LiteralKind(str, enum.Enum):
    BOOL = "bool"
    NUMBER = "number"
    STRING = "string"
    HEX_STRING = "hexString"
    UNICODE_STRING = "unicodeString"


class YulLiteralValueKind(str, enum.Enum):
    NUMBER = "number"
    STRING = "string"
    BOOL = "bool"


class YulLiteralHexValueKind(str, enum.Enum):
    NUMBER = "number"
    STRING = "string"
    BOOL = "bool"


# Function call
class FunctionCallKind(str, enum.Enum):
    FUNCTION_CALL = "functionCall"
    TYPE_CONVERSION = "typeConversion"
    STRUCT_CONSTRUCTOR_CALL = "structConstructorCall"


# Compound types
class StorageLocation(str, enum.Enum):
    CALLDATA = "calldata"
    DEFAULT = "default"
    MEMORY = "memory"
    STORAGE = "storage"


# Operations
class UnaryOpOperator(str, enum.Enum):
    PLUS_PLUS = r"++"
    MINUS_MINUS = r"--"
    MINUS = r"-"
    NOT = r"!"
    TILDE = r"~"
    DELETE = "delete"


class AssignmentOperator(str, enum.Enum):
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


class BinaryOpOperator(str, enum.Enum):
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
class InlineAssemblyEvmVersion(str, enum.Enum):
    HOMESTEAD = "homestead"
    TANGERINE_WHISTLE = "tangerineWhistle"
    SPURIOUS_DRAGON = "spuriousDragon"
    BYZANTIUM = "byzantium"
    CONSTANTINOPLE = "constantinople"
    PETERSBURG = "petersburg"
    ISTANBUL = "istanbul"
    BERLIN = "berlin"
    LONDON = "london"


class InlineAssemblySuffix(str, enum.Enum):
    SLOT = "slot"
    OFFSET = "offset"
    LENGTH = "length"
    ADDRESS = "address"
    SELECTOR = "selector"


class InlineAssemblyFlag(str, enum.Enum):
    MEMORY_SAFE = "memory-safe"
