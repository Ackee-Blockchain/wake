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

    BLOCK_BASEFEE = -100
    BLOCK_CHAINID = -101
    BLOCK_COINBASE = -102
    BLOCK_DIFFICULTY = -103
    BLOCK_GASLIMIT = -104
    BLOCK_NUMBER = -105
    BLOCK_TIMESTAMP = -106

    MSG_DATA = -200
    MSG_SENDER = -201
    MSG_SIG = -202
    MSG_VALUE = -203

    TX_GASPRICE = -300
    TX_ORIGIN = -301

    ABI_DECODE = -400
    ABI_ENCODE = -401
    ABI_ENCODE_PACKED = -402
    ABI_ENCODE_WITH_SELECTOR = -403
    ABI_ENCODE_WITH_SIGNATURE = -404
    ABI_ENCODE_CALL = -405

    BYTES_CONCAT = -500
    BYTES_LENGTH = -501

    STRING_CONCAT = -600

    ADDRESS_BALANCE = -700
    ADDRESS_CODE = -701
    ADDRESS_CODEHASH = -702
    ADDRESS_TRANSFER = -703
    ADDRESS_SEND = -704
    ADDRESS_CALL = -705
    ADDRESS_DELEGATECALL = -706
    ADDRESS_STATICCALL = -707

    # available for contracts and interfaces
    TYPE_NAME = -800
    TYPE_CREATION_CODE = -801
    TYPE_RUNTIME_CODE = -802
    # available for interfaces only
    TYPE_INTERFACE_ID = -803
    # available for integers
    TYPE_MIN = -804
    TYPE_MAX = -805

    ARRAY_LENGTH = -900
    ARRAY_PUSH = -901
    ARRAY_POP = -902

    FUNCTION_SELECTOR = -1000
    FUNCTION_VALUE = -1001
    FUNCTION_GAS = -1002


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
class DataLocation(str, enum.Enum):
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


class ModifiesStateFlag(enum.IntFlag):
    MODIFIES_STATE_VAR = 1
    EMITS = 2
    SENDS_ETHER = 4
    DEPLOYS_CONTRACT = 8
    SELFDESTRUCTS = 16
    PERFORMS_CALL = 32
    PERFORMS_DELEGATECALL = 64
    CALLS_UNIMPLEMENTED_NONPAYABLE_FUNCTION = 128
    CALLS_UNIMPLEMENTED_PAYABLE_FUNCTION = 256

    def __repr__(self):
        if self.value == 0:
            return f"{self.__class__.__name__}(0)"
        flags = [f for f in self.__class__ if f in self]
        return " | ".join(f.name or "" for f in flags)

    __str__ = __repr__
