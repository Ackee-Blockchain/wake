from enum import IntEnum, IntFlag

from wake.utils import StrEnum


class GlobalSymbol(IntEnum):
    """
    Global symbols of the Solidity language. Symbols with identifiers from `-1` to `-99` are codified by the compiler and can only be referenced by [Identifier][wake.ir.expressions.identifier.Identifier] nodes.
    Other symbols are not officially codified by the compiler, but Wake also defines identifiers for them. These symbols can only be referenced by [MemberAccess][wake.ir.expressions.member_access.MemberAccess] nodes.
    See the [Solidity docs](https://docs.soliditylang.org/en/latest/units-and-global-variables.html#special-variables-and-functions) for (an incomplete) list of global symbols and their descriptions.
    """

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
    BLOCK_PREVRANDAO = -107

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
    BYTES_PUSH = -502

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
    FUNCTION_ADDRESS = -1003

    USER_DEFINED_VALUE_TYPE_WRAP = -1100
    USER_DEFINED_VALUE_TYPE_UNWRAP = -1101


# Contracts
class ContractKind(StrEnum):
    """
    Kind of a [ContractDefinition][wake.ir.declarations.contract_definition.ContractDefinition] declaration node.
    """

    CONTRACT = "contract"
    INTERFACE = "interface"
    LIBRARY = "library"


# State variables
class Mutability(StrEnum):
    """
    Mutability of a [VariableDeclaration][wake.ir.declarations.variable_declaration.VariableDeclaration] declaration node.
    """

    MUTABLE = "mutable"
    IMMUTABLE = "immutable"
    CONSTANT = "constant"


# Functions
class FunctionKind(StrEnum):
    """
    Kind of a [FunctionDefinition][wake.ir.declarations.function_definition.FunctionDefinition] declaration node.
    """

    FUNCTION = "function"
    RECEIVE = "receive"
    CONSTRUCTOR = "constructor"
    FALLBACK = "fallback"
    FREE_FUNCTION = "freeFunction"
    """
    Function defined outside of a contract.
    """


class Visibility(StrEnum):
    """
    Visibility of:

    - [FunctionTypeName][wake.ir.type_names.function_type_name.FunctionTypeName] type name,
    - [FunctionDefinition][wake.ir.declarations.function_definition.FunctionDefinition], [ModifierDefinition][wake.ir.declarations.modifier_definition.ModifierDefinition], [StructDefinition][wake.ir.declarations.struct_definition.StructDefinition] and [VariableDeclaration][wake.ir.declarations.variable_declaration.VariableDeclaration] declarations.
    """

    EXTERNAL = "external"
    PUBLIC = "public"
    INTERNAL = "internal"
    PRIVATE = "private"


class StateMutability(StrEnum):
    """
    State mutability of:

    - [Function][wake.ir.types.Function] type,
    - [FunctionDefinition][wake.ir.declarations.function_definition.FunctionDefinition] declaration,
    - [ElementaryTypeName][wake.ir.type_names.elementary_type_name.ElementaryTypeName] and [FunctionTypeName][wake.ir.type_names.function_type_name.FunctionTypeName] type names.

    In the case of [ElementaryTypeName][wake.ir.type_names.elementary_type_name.ElementaryTypeName], the state mutability is specified only for the `address` type and can be either [NONPAYABLE][wake.ir.enums.StateMutability.NONPAYABLE] or [PAYABLE][wake.ir.enums.StateMutability.PAYABLE].
    """

    PAYABLE = "payable"
    PURE = "pure"
    NONPAYABLE = "nonpayable"
    VIEW = "view"


class ModifierInvocationKind(StrEnum):
    """
    Kind of a [ModifierInvocation][wake.ir.meta.modifier_invocation.ModifierInvocation] meta node.
    """

    MODIFIER_INVOCATION = "modifierInvocation"
    BASE_CONSTRUCTOR_SPECIFIER = "baseConstructorSpecifier"


# Literals
class LiteralKind(StrEnum):
    """
    Kind of a [Literal][wake.ir.expressions.literal.Literal] expression node.
    """

    BOOL = "bool"
    NUMBER = "number"
    STRING = "string"
    HEX_STRING = "hexString"
    UNICODE_STRING = "unicodeString"


class YulLiteralKind(StrEnum):
    """
    Kind of a [YulLiteral][wake.ir.yul.literal.YulLiteral] node.
    """

    NUMBER = "number"
    STRING = "string"
    BOOL = "bool"


# Function call
class FunctionCallKind(StrEnum):
    """
    Kind of a [FunctionCall][wake.ir.expressions.function_call.FunctionCall] expression node.
    """

    FUNCTION_CALL = "functionCall"
    """
    Represents also an error call, event call and [NewExpression][wake.ir.expressions.new_expression.NewExpression] call.
    """
    TYPE_CONVERSION = "typeConversion"
    STRUCT_CONSTRUCTOR_CALL = "structConstructorCall"


# Compound types
class DataLocation(StrEnum):
    """
    Data location of a [VariableDeclaration][wake.ir.declarations.variable_declaration.VariableDeclaration] node.
    It also specifies the data location of the following types:

    - [Array][wake.ir.types.Array],
    - [Bytes][wake.ir.types.Bytes],
    - [String][wake.ir.types.String],
    - [Struct][wake.ir.types.Struct].
    """

    CALLDATA = "calldata"
    DEFAULT = "default"
    """
    Set only in [VariableDeclaration][wake.ir.declarations.variable_declaration.VariableDeclaration] nodes when the data location is not specified (and the compiler even does not allow it).
    """
    MEMORY = "memory"
    STORAGE = "storage"


# Operations
class UnaryOpOperator(StrEnum):
    """
    Unary operation operator used in an [UnaryOperation][wake.ir.expressions.unary_operation.UnaryOperation] expression.
    """

    PLUS_PLUS = r"++"
    MINUS_MINUS = r"--"
    MINUS = r"-"
    NOT = r"!"
    TILDE = r"~"
    DELETE = "delete"


class AssignmentOperator(StrEnum):
    """
    Assignment operator used in an [Assignment][wake.ir.expressions.assignment.Assignment] expression.
    """

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
    """
    Binary operation operator used in a [BinaryOperation][wake.ir.expressions.binary_operation.BinaryOperation] expression.
    """

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
    PARIS = "paris"
    SHANGHAI = "shanghai"


class InlineAssemblySuffix(StrEnum):
    SLOT = "slot"
    OFFSET = "offset"
    LENGTH = "length"
    ADDRESS = "address"
    SELECTOR = "selector"


class InlineAssemblyFlag(StrEnum):
    MEMORY_SAFE = "memory-safe"


class ModifiesStateFlag(IntFlag):
    """
    Flag enum describing how an expression ([ExpressionAbc][wake.ir.expressions.abc.ExpressionAbc]) or statement ([StatementAbc][wake.ir.statements.abc.StatementAbc]) modifies the blockchain state.
    """

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


class FunctionTypeKind(StrEnum):
    """
    Kind of a [Function][wake.ir.types.Function] type.
    """

    DECLARATION = "declaration"
    INTERNAL = "internal"
    EXTERNAL = "external"
    DELEGATE_CALL = "delegatecall"
    BARE_CALL = "barecall"
    BARE_CALL_CODE = "barecallcode"
    BARE_DELEGATE_CALL = "baredelegatecall"
    BARE_STATIC_CALL = "barestaticcall"
    CREATION = "creation"
    SEND = "send"
    TRANSFER = "transfer"
    KECCAK256 = "keccak256"
    SELFDESTRUCT = "selfdestruct"
    REVERT = "revert"
    EC_RECOVER = "ecrecover"
    SHA256 = "sha256"
    RIPEMD160 = "ripemd160"
    LOG0 = "log0"
    LOG1 = "log1"
    LOG2 = "log2"
    LOG3 = "log3"
    LOG4 = "log4"
    GAS_LEFT = "gasleft"
    EVENT = "event"
    ERROR = "error"
    WRAP = "wrap"
    UNWRAP = "unwrap"
    SET_GAS = "setgas"
    SET_VALUE = "setvalue"
    BLOCK_HASH = "blockhash"
    ADD_MOD = "addmod"
    MUL_MOD = "mulmod"
    ARRAY_PUSH = "arraypush"
    ARRAY_POP = "arraypop"
    BYTE_ARRAY_PUSH = "bytearraypush"
    BYTES_CONCAT = "bytesconcat"
    STRING_CONCAT = "stringconcat"
    OBJECT_CREATION = "objectcreation"
    ASSERT = "assert"
    REQUIRE = "require"
    ABI_ENCODE = "abiencode"
    ABI_ENCODE_PACKED = "abiencodepacked"
    ABI_ENCODE_WITH_SELECTOR = "abiencodewithselector"
    ABI_ENCODE_CALL = "abiencodecall"
    ABI_ENCODE_WITH_SIGNATURE = "abiencodewithsignature"
    ABI_DECODE = "abidecode"
    META_TYPE = "metatype"


class MagicTypeKind(StrEnum):
    """
    Kind of a [Magic][wake.ir.types.Magic] type.
    """

    BLOCK = "block"
    MESSAGE = "message"
    TRANSACTION = "transaction"
    ABI = "abi"
    META_TYPE = "meta_type"
