from __future__ import annotations

import enum
import re
from abc import ABC
from typing import TYPE_CHECKING, Optional, Tuple

if TYPE_CHECKING:
    from woke.ast.ir.declaration.contract_definition import ContractDefinition
    from woke.ast.ir.declaration.enum_definition import EnumDefinition
    from woke.ast.ir.declaration.struct_definition import StructDefinition
    from woke.ast.ir.declaration.user_defined_value_type_definition import (
        UserDefinedValueTypeDefinition,
    )

from woke.ast.enums import DataLocation, StateMutability
from woke.ast.ir.reference_resolver import ReferenceResolver
from woke.ast.nodes import AstNodeId
from woke.utils.string import StringReader

NUMBER_RE = re.compile(r"^(?P<number>[0-9]+)")
HEX_RE = re.compile(r"^(?P<hex>[0-9a-fA-F]+)")
IDENTIFIER_RE = re.compile(r"^\$_(?P<identifier>[a-zA-Z\$_][a-zA-Z0-9\$_]*)_\$")


class ExpressionTypeAbc(ABC):
    @classmethod
    def from_type_identifier(
        cls,
        type_identifier: StringReader,
        reference_resolver: ReferenceResolver,
        cu_hash: bytes,
    ) -> Optional["ExpressionTypeAbc"]:
        if type_identifier.startswith("t_address"):
            return Address(type_identifier)
        elif type_identifier.startswith("t_bool"):
            return Bool(type_identifier)
        elif type_identifier.startswith("t_int"):
            return Int(type_identifier)
        elif type_identifier.startswith("t_uint"):
            return UInt(type_identifier)
        elif type_identifier.startswith("t_stringliteral_"):
            return StringLiteral(type_identifier)
        elif type_identifier.startswith("t_string_"):
            return String(type_identifier)
        elif type_identifier.startswith("t_bytes_"):
            return Bytes(type_identifier)
        # must go after t_bytes_ !!
        elif type_identifier.startswith("t_bytes"):
            return FixedBytes(type_identifier)
        elif type_identifier.startswith("t_function"):
            return Function(type_identifier, reference_resolver, cu_hash)
        elif type_identifier.startswith("t_tuple"):
            return Tuple_(type_identifier, reference_resolver, cu_hash)
        elif type_identifier.startswith("t_type"):
            return Type(type_identifier, reference_resolver, cu_hash)
        elif type_identifier.startswith("t_rational"):
            return Rational(type_identifier)
        elif type_identifier.startswith("t_modifier"):
            return Modifier(type_identifier, reference_resolver, cu_hash)
        elif type_identifier.startswith("t_array"):
            return Array(type_identifier, reference_resolver, cu_hash)
        elif type_identifier.startswith("t_mapping"):
            return Mapping(type_identifier, reference_resolver, cu_hash)
        elif type_identifier.startswith("t_contract") or type_identifier.startswith(
            "t_super"
        ):
            return Contract(type_identifier, reference_resolver, cu_hash)
        elif type_identifier.startswith("t_struct"):
            return Struct(type_identifier, reference_resolver, cu_hash)
        elif type_identifier.startswith("t_enum"):
            return Enum(type_identifier, reference_resolver, cu_hash)
        elif type_identifier.startswith("t_magic"):
            return Magic(type_identifier, reference_resolver, cu_hash)
        elif type_identifier.startswith("t_userDefinedValueType"):
            return UserDefinedValueType(type_identifier, reference_resolver, cu_hash)
        elif type_identifier.startswith("t_module"):
            return Module(type_identifier)
        elif type_identifier.startswith("t_fixed"):
            return Fixed(type_identifier)
        elif type_identifier.startswith("t_ufixed"):
            return UFixed(type_identifier)
        else:
            return None


def _parse_list(
    type_identifier: StringReader, reference_resolver: ReferenceResolver, cu_hash: bytes
) -> Tuple[Optional[ExpressionTypeAbc], ...]:
    type_identifier.read("$_")
    # handle empty list
    if not type_identifier.startswith("_$_") and type_identifier.startswith("_$"):
        type_identifier.read("_$")
        return tuple()

    items = [
        ExpressionTypeAbc.from_type_identifier(
            type_identifier, reference_resolver, cu_hash
        )
    ]
    while not type_identifier.startswith("_$_$") and type_identifier.startswith("_$_"):
        type_identifier.read("_$_")
        items.append(
            ExpressionTypeAbc.from_type_identifier(
                type_identifier, reference_resolver, cu_hash
            )
        )
    type_identifier.read("_$")
    return tuple(items)


def _parse_user_identifier(type_identifier: StringReader) -> str:
    type_identifier.read("$_")

    for match in re.finditer(r"_\$", type_identifier.data):
        if (
            len(type_identifier) < match.start() + 4
            or type_identifier.data[match.start() : match.start() + 4] != "_$$$"
        ):
            name = type_identifier.data[: match.start()]
            type_identifier.read(name + "_$")
            return name.replace("$$$", "$")
    assert False, "Failed to parse user identifier"


class Address(ExpressionTypeAbc):
    __is_payable: bool

    def __init__(self, type_identifier: StringReader):
        type_identifier.read("t_address")

        if type_identifier.startswith("_payable"):
            type_identifier.read("_payable")
            self.__is_payable = True
        else:
            self.__is_payable = False

    @property
    def is_payable(self) -> bool:
        return self.__is_payable


class Bool(ExpressionTypeAbc):
    def __init__(self, type_identifier: StringReader):
        type_identifier.read("t_bool")


class IntAbc(ExpressionTypeAbc):
    pass


class Int(IntAbc):
    __bits_count: int

    def __init__(self, type_identifier: StringReader):
        type_identifier.read("t_int")
        match = NUMBER_RE.match(type_identifier.data)
        assert match is not None
        number = match.group("number")
        type_identifier.read(number)
        self.__bits_count = int(number)

    @property
    def bits_count(self) -> int:
        return self.__bits_count


class UInt(IntAbc):
    __bits_count: int

    def __init__(self, type_identifier: StringReader):
        type_identifier.read("t_uint")
        match = NUMBER_RE.match(type_identifier.data)
        assert match is not None
        number = match.group("number")
        type_identifier.read(number)
        self.__bits_count = int(number)

    @property
    def bits_count(self) -> int:
        return self.__bits_count


class FixedAbc(ExpressionTypeAbc):
    pass


class Fixed(FixedAbc):
    __total_bits: int
    __fractional_digits: int

    def __init__(self, type_identifier: StringReader):
        type_identifier.read("t_fixed")
        match = NUMBER_RE.match(type_identifier.data)
        assert match is not None
        total_bits = match.group("number")
        type_identifier.read(total_bits)
        self.__total_bits = int(total_bits)

        type_identifier.read("x")

        match = NUMBER_RE.match(type_identifier.data)
        assert match is not None
        fractional_digits = match.group("number")
        type_identifier.read(fractional_digits)
        self.__fractional_digits = int(fractional_digits)

    @property
    def total_bits(self) -> int:
        return self.__total_bits

    @property
    def fractional_digits(self) -> int:
        return self.__fractional_digits


class UFixed(FixedAbc):
    __total_bits: int
    __fractional_digits: int

    def __init__(self, type_identifier: StringReader):
        type_identifier.read("t_ufixed")
        match = NUMBER_RE.match(type_identifier.data)
        assert match is not None
        total_bits = match.group("number")
        type_identifier.read(total_bits)
        self.__total_bits = int(total_bits)

        type_identifier.read("x")

        match = NUMBER_RE.match(type_identifier.data)
        assert match is not None
        fractional_digits = match.group("number")
        type_identifier.read(fractional_digits)
        self.__fractional_digits = int(fractional_digits)

    @property
    def total_bits(self) -> int:
        return self.__total_bits

    @property
    def fractional_digits(self) -> int:
        return self.__fractional_digits


class StringLiteral(ExpressionTypeAbc):
    __keccak256_hash: bytes

    def __init__(self, type_identifier: StringReader):
        type_identifier.read("t_stringliteral_")
        match = HEX_RE.match(type_identifier.data)
        assert match is not None
        hex = match.group("hex")
        type_identifier.read(hex)
        self.__keccak256_hash = bytes.fromhex(hex)

    @property
    def keccak256_hash(self) -> bytes:
        return self.__keccak256_hash


class String(ExpressionTypeAbc):
    __data_location: DataLocation
    __is_pointer: bool
    __is_slice: bool

    def __init__(self, type_identifier: StringReader):
        type_identifier.read("t_string")
        if type_identifier.startswith("_storage"):
            self.__data_location = DataLocation.STORAGE
            type_identifier.read("_storage")
        elif type_identifier.startswith("_memory"):
            self.__data_location = DataLocation.MEMORY
            type_identifier.read("_memory")
        elif type_identifier.startswith("_calldata"):
            self.__data_location = DataLocation.CALLDATA
            type_identifier.read("_calldata")
        else:
            assert False, f"Unexpected string type data location {type_identifier}"

        if type_identifier.startswith("_ptr"):
            self.__is_pointer = True
            type_identifier.read("_ptr")
        else:
            self.__is_pointer = False

        if type_identifier.startswith("_slice"):
            self.__is_slice = True
            type_identifier.read("_slice")
        else:
            self.__is_slice = False

    @property
    def data_location(self) -> DataLocation:
        """Can be either STORAGE, MEMORY, or CALLDATA"""
        return self.__data_location

    @property
    def is_pointer(self) -> bool:
        return self.__is_pointer

    @property
    def is_slice(self) -> bool:
        return self.__is_slice


class Bytes(ExpressionTypeAbc):
    __data_location: DataLocation
    __is_pointer: bool
    __is_slice: bool

    def __init__(self, type_identifier: StringReader):
        type_identifier.read("t_bytes")
        if type_identifier.startswith("_storage"):
            self.__data_location = DataLocation.STORAGE
            type_identifier.read("_storage")
        elif type_identifier.startswith("_memory"):
            self.__data_location = DataLocation.MEMORY
            type_identifier.read("_memory")
        elif type_identifier.startswith("_calldata"):
            self.__data_location = DataLocation.CALLDATA
            type_identifier.read("_calldata")
        else:
            assert False, f"Unexpected string type data location {type_identifier}"

        if type_identifier.startswith("_ptr"):
            self.__is_pointer = True
            type_identifier.read("_ptr")
        else:
            self.__is_pointer = False

        if type_identifier.startswith("_slice"):
            self.__is_slice = True
            type_identifier.read("_slice")
        else:
            self.__is_slice = False

    @property
    def data_location(self) -> DataLocation:
        """Can be either STORAGE, MEMORY, or CALLDATA"""
        return self.__data_location

    @property
    def is_pointer(self) -> bool:
        return self.__is_pointer

    @property
    def is_slice(self) -> bool:
        return self.__is_slice


class FixedBytes(ExpressionTypeAbc):
    __bytes_count: int

    def __init__(self, type_identifier: StringReader):
        type_identifier.read("t_bytes")
        match = NUMBER_RE.match(type_identifier.data)
        assert match is not None
        number = match.group("number")
        type_identifier.read(number)
        self.__bytes_count = int(number)

    @property
    def bytes_count(self) -> int:
        return self.__bytes_count


class FunctionExpressionKind(str, enum.Enum):
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
    SELFDESCTRUCT = "selfdestruct"
    REVERT = "revert"
    EC_RECOVER = "ecrecover"
    SHA256 = "sha256"
    RIPEMD160 = "ripemd160"
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


class Function(ExpressionTypeAbc):
    __kind: FunctionExpressionKind
    __state_mutability: StateMutability
    __parameters: Tuple[ExpressionTypeAbc, ...]
    __return_parameters: Tuple[ExpressionTypeAbc, ...]
    __gas_set: bool
    __value_set: bool
    __salt_set: bool
    __bound_to: Optional[Tuple[ExpressionTypeAbc, ...]]

    def __init__(
        self,
        type_identifier: StringReader,
        reference_resolver: ReferenceResolver,
        cu_hash: bytes,
    ):
        type_identifier.read("t_function_")

        matched = []
        for kind in FunctionExpressionKind:
            if type_identifier.startswith(kind):
                matched.append(kind)
        assert len(matched) >= 1, f"Unexpected function kind {type_identifier}"
        self.__kind = FunctionExpressionKind(max(matched, key=len))
        type_identifier.read(self.__kind)

        if type_identifier.startswith("_payable"):
            self.__state_mutability = StateMutability.PAYABLE
            type_identifier.read("_payable")
        elif type_identifier.startswith("_pure"):
            self.__state_mutability = StateMutability.PURE
            type_identifier.read("_pure")
        elif type_identifier.startswith("_nonpayable"):
            self.__state_mutability = StateMutability.NONPAYABLE
            type_identifier.read("_nonpayable")
        elif type_identifier.startswith("_view"):
            self.__state_mutability = StateMutability.VIEW
            type_identifier.read("_view")
        else:
            assert False, f"Unexpected function state mutability {type_identifier}"

        parameters = _parse_list(type_identifier, reference_resolver, cu_hash)
        assert not any(param is None for param in parameters)
        self.__parameters = parameters  # type: ignore

        type_identifier.read("returns")
        return_parameters = _parse_list(type_identifier, reference_resolver, cu_hash)
        assert not any(param is None for param in return_parameters)
        self.__return_parameters = return_parameters  # type: ignore

        if type_identifier.startswith("gas"):
            self.__gas_set = True
            type_identifier.read("gas")
        else:
            self.__gas_set = False

        if type_identifier.startswith("value"):
            self.__value_set = True
            type_identifier.read("value")
        else:
            self.__value_set = False

        if type_identifier.startswith("salt"):
            self.__salt_set = True
            type_identifier.read("salt")
        else:
            self.__salt_set = False

        if type_identifier.startswith("bound_to"):
            type_identifier.read("bound_to")
            bound_to = _parse_list(type_identifier, reference_resolver, cu_hash)
            assert not any(param is None for param in bound_to)
            self.__bound_to = bound_to  # type: ignore
        else:
            self.__bound_to = None

    @property
    def kind(self) -> FunctionExpressionKind:
        return self.__kind

    @property
    def state_mutability(self) -> StateMutability:
        return self.__state_mutability

    @property
    def parameters(self) -> Tuple[ExpressionTypeAbc, ...]:
        return self.__parameters

    @property
    def return_parameters(self) -> Tuple[ExpressionTypeAbc, ...]:
        return self.__return_parameters

    @property
    def gas_set(self) -> bool:
        return self.__gas_set

    @property
    def value_set(self) -> bool:
        return self.__value_set

    @property
    def salt_set(self) -> bool:
        return self.__salt_set

    @property
    def bound_to(self) -> Optional[Tuple[ExpressionTypeAbc, ...]]:
        return self.__bound_to


class Tuple_(ExpressionTypeAbc):
    __components: Tuple[Optional[ExpressionTypeAbc], ...]

    def __init__(
        self,
        type_identifier: StringReader,
        reference_resolver: ReferenceResolver,
        cu_hash: bytes,
    ):
        type_identifier.read("t_tuple")
        self.__components = _parse_list(type_identifier, reference_resolver, cu_hash)

    @property
    def components(self) -> Tuple[Optional[ExpressionTypeAbc], ...]:
        return self.__components


class Type(ExpressionTypeAbc):
    __actual_type: ExpressionTypeAbc

    def __init__(
        self,
        type_identifier: StringReader,
        reference_resolver: ReferenceResolver,
        cu_hash: bytes,
    ):
        type_identifier.read("t_type")
        actual_type = _parse_list(type_identifier, reference_resolver, cu_hash)
        assert len(actual_type) == 1 and actual_type[0] is not None
        self.__actual_type = actual_type[0]

    @property
    def actual_type(self) -> ExpressionTypeAbc:
        return self.__actual_type


class Rational(ExpressionTypeAbc):
    __numerator: int
    __denominator: int

    def __init__(self, type_identifier: StringReader):
        type_identifier.read("t_rational_")

        if type_identifier.startswith("minus_"):
            type_identifier.read("minus_")
            self.__numerator = -1
        else:
            self.__numerator = 1

        match = NUMBER_RE.match(type_identifier.data)
        assert match is not None, f"{type_identifier} is not a valid rational"
        number = match.group("number")
        type_identifier.read(number)
        self.__numerator *= int(number)

        type_identifier.read("_by_")

        match = NUMBER_RE.match(type_identifier.data)
        assert match is not None, f"{type_identifier} is not a valid rational"
        number = match.group("number")
        type_identifier.read(number)
        self.__denominator = int(number)

    @property
    def numerator(self) -> int:
        return self.__numerator

    @property
    def denominator(self) -> int:
        return self.__denominator


class Modifier(ExpressionTypeAbc):
    __parameters: Tuple[ExpressionTypeAbc, ...]

    def __init__(
        self,
        type_identifier: StringReader,
        reference_resolver: ReferenceResolver,
        cu_hash: bytes,
    ):
        type_identifier.read("t_modifier")
        parameters = _parse_list(type_identifier, reference_resolver, cu_hash)
        assert not any(param is None for param in parameters)
        self.__parameters = parameters  # type: ignore

    @property
    def parameters(self) -> Tuple[ExpressionTypeAbc, ...]:
        return self.__parameters


class Array(ExpressionTypeAbc):
    __base_type: ExpressionTypeAbc
    __length: Optional[int]
    __data_location: DataLocation
    __is_pointer: bool
    __is_slice: bool

    def __init__(
        self,
        type_identifier: StringReader,
        reference_resolver: ReferenceResolver,
        cu_hash: bytes,
    ):
        type_identifier.read("t_array")
        base_type = _parse_list(type_identifier, reference_resolver, cu_hash)
        assert (
            len(base_type) == 1 and base_type[0] is not None
        ), f"Unexpected array base type {type_identifier}"
        self.__base_type = base_type[0]

        if type_identifier.startswith("dyn"):
            self.__length = None
            type_identifier.read("dyn")
        else:
            match = NUMBER_RE.match(type_identifier.data)
            assert match is not None, f"{type_identifier} is not a valid array length"
            self.__length = int(match.group("number"))
            type_identifier.read(match.group("number"))

        if type_identifier.startswith("_storage"):
            self.__data_location = DataLocation.STORAGE
            type_identifier.read("_storage")
        elif type_identifier.startswith("_memory"):
            self.__data_location = DataLocation.MEMORY
            type_identifier.read("_memory")
        elif type_identifier.startswith("_calldata"):
            self.__data_location = DataLocation.CALLDATA
            type_identifier.read("_calldata")
        else:
            assert False, f"Unexpected array type data location {type_identifier}"

        if type_identifier.startswith("_ptr"):
            self.__is_pointer = True
            type_identifier.read("_ptr")
        else:
            self.__is_pointer = False

        if type_identifier.startswith("_slice"):
            self.__is_slice = True
            type_identifier.read("_slice")
        else:
            self.__is_slice = False

    @property
    def base_type(self) -> ExpressionTypeAbc:
        return self.__base_type

    @property
    def length(self) -> Optional[int]:
        return self.__length

    @property
    def data_location(self) -> DataLocation:
        return self.__data_location

    @property
    def is_pointer(self) -> bool:
        return self.__is_pointer

    @property
    def is_slice(self) -> bool:
        return self.__is_slice


class Mapping(ExpressionTypeAbc):
    __key_type: ExpressionTypeAbc
    __value_type: ExpressionTypeAbc

    def __init__(
        self,
        type_identifier: StringReader,
        reference_resolver: ReferenceResolver,
        cu_hash: bytes,
    ):
        type_identifier.read("t_mapping")
        key_value = _parse_list(type_identifier, reference_resolver, cu_hash)
        assert len(key_value) == 2, f"{type_identifier} is not a valid mapping"
        assert key_value[0] is not None, f"{type_identifier} is not a valid mapping"
        assert key_value[1] is not None, f"{type_identifier} is not a valid mapping"
        self.__key_type = key_value[0]
        self.__value_type = key_value[1]

    @property
    def key_type(self) -> ExpressionTypeAbc:
        return self.__key_type

    @property
    def value_type(self) -> ExpressionTypeAbc:
        return self.__value_type


class Contract(ExpressionTypeAbc):
    __is_super: bool
    __name: str
    __ast_id: AstNodeId
    __reference_resolver: ReferenceResolver
    __cu_hash: bytes

    def __init__(
        self,
        type_identifier: StringReader,
        reference_resolver: ReferenceResolver,
        cu_hash: bytes,
    ):
        if type_identifier.startswith("t_contract"):
            self.__is_super = False
            type_identifier.read("t_contract")
        elif type_identifier.startswith("t_super"):
            self.__is_super = True
            type_identifier.read("t_super")
        else:
            assert False, f"Unexpected contract type {type_identifier}"
        self.__name = _parse_user_identifier(type_identifier)

        match = NUMBER_RE.match(type_identifier.data)
        assert match is not None, f"{type_identifier} is not a valid contract"
        self.__ast_id = AstNodeId(int(match.group("number")))
        type_identifier.read(match.group("number"))

        self.__reference_resolver = reference_resolver
        self.__cu_hash = cu_hash

    @property
    def is_super(self) -> bool:
        return self.__is_super

    @property
    def name(self) -> str:
        return self.__name

    @property
    def ir_node(self) -> ContractDefinition:
        node = self.__reference_resolver.resolve_node(self.__ast_id, self.__cu_hash)
        assert isinstance(node, ContractDefinition)
        return node


class Struct(ExpressionTypeAbc):
    __name: str
    __ast_id: AstNodeId
    __data_location: DataLocation
    __is_pointer: bool
    __reference_resolver: ReferenceResolver
    __cu_hash: bytes

    def __init__(
        self,
        type_identifier: StringReader,
        reference_resolver: ReferenceResolver,
        cu_hash: bytes,
    ):
        type_identifier.read("t_struct")
        self.__name = _parse_user_identifier(type_identifier)

        match = NUMBER_RE.match(type_identifier.data)
        assert match is not None, f"{type_identifier} is not a valid struct"
        self.__ast_id = AstNodeId(int(match.group("number")))
        type_identifier.read(match.group("number"))

        if type_identifier.startswith("_storage"):
            self.__data_location = DataLocation.STORAGE
            type_identifier.read("_storage")
        elif type_identifier.startswith("_memory"):
            self.__data_location = DataLocation.MEMORY
            type_identifier.read("_memory")
        elif type_identifier.startswith("_calldata"):
            self.__data_location = DataLocation.CALLDATA
            type_identifier.read("_calldata")
        else:
            assert False, f"Unexpected array type data location {type_identifier}"

        if type_identifier.startswith("_ptr"):
            self.__is_pointer = True
            type_identifier.read("_ptr")
        else:
            self.__is_pointer = False

        self.__reference_resolver = reference_resolver
        self.__cu_hash = cu_hash

    @property
    def name(self) -> str:
        return self.__name

    @property
    def data_location(self) -> DataLocation:
        return self.__data_location

    @property
    def is_pointer(self) -> bool:
        return self.__is_pointer

    @property
    def ir_node(self) -> StructDefinition:
        node = self.__reference_resolver.resolve_node(self.__ast_id, self.__cu_hash)
        assert isinstance(node, StructDefinition)
        return node


class Enum(ExpressionTypeAbc):
    __name: str
    __ast_id: AstNodeId
    __reference_resolver: ReferenceResolver
    __cu_hash: bytes

    def __init__(
        self,
        type_identifier: StringReader,
        reference_resolver: ReferenceResolver,
        cu_hash: bytes,
    ):
        type_identifier.read("t_enum")
        self.__name = _parse_user_identifier(type_identifier)

        match = NUMBER_RE.match(type_identifier.data)
        assert match is not None, f"{type_identifier} is not a valid enum"
        self.__ast_id = AstNodeId(int(match.group("number")))
        type_identifier.read(match.group("number"))

        self.__reference_resolver = reference_resolver
        self.__cu_hash = cu_hash

    @property
    def name(self) -> str:
        return self.__name

    @property
    def ir_node(self) -> EnumDefinition:
        node = self.__reference_resolver.resolve_node(self.__ast_id, self.__cu_hash)
        assert isinstance(node, EnumDefinition)
        return node


class MagicExpressionKind(str, enum.Enum):
    BLOCK = "block"
    MESSAGE = "message"
    TRANSACTION = "transaction"
    ABI = "abi"
    META_TYPE = "meta_type"


class Magic(ExpressionTypeAbc):
    __kind: MagicExpressionKind
    __meta_argument_type: Optional[ExpressionTypeAbc]

    def __init__(
        self,
        type_identifier: StringReader,
        reference_resolver: ReferenceResolver,
        cu_hash: bytes,
    ):
        type_identifier.read("t_magic_")

        matched = False
        for kind in MagicExpressionKind:
            if type_identifier.startswith(kind):
                self.__kind = MagicExpressionKind(kind)
                type_identifier.read(kind)
                matched = True
                break
        assert matched, f"Unexpected magic kind {type_identifier}"

        if self.__kind == MagicExpressionKind.META_TYPE:
            type_identifier.read("_")
            meta_argument_type = ExpressionTypeAbc.from_type_identifier(
                type_identifier, reference_resolver, cu_hash
            )
            assert meta_argument_type is not None
            self.__meta_argument_type = meta_argument_type
        else:
            self.__meta_argument_type = None

    @property
    def kind(self) -> MagicExpressionKind:
        return self.__kind

    @property
    def meta_argument_type(self) -> Optional[ExpressionTypeAbc]:
        """
        Is set if the magic expression is a meta type.
        """
        return self.__meta_argument_type


class UserDefinedValueType(ExpressionTypeAbc):
    __name: str
    __ast_id: AstNodeId
    __reference_resolver: ReferenceResolver
    __cu_hash: bytes

    def __init__(
        self,
        type_identifier: StringReader,
        reference_resolver: ReferenceResolver,
        cu_hash: bytes,
    ):
        type_identifier.read("t_userDefinedValueType")
        self.__name = _parse_user_identifier(type_identifier)

        match = NUMBER_RE.match(type_identifier.data)
        assert match is not None, f"{type_identifier} is not a valid enum"
        self.__ast_id = AstNodeId(int(match.group("number")))
        type_identifier.read(match.group("number"))

        self.__reference_resolver = reference_resolver
        self.__cu_hash = cu_hash

    @property
    def name(self) -> str:
        return self.__name

    @property
    def ir_node(self) -> UserDefinedValueTypeDefinition:
        node = self.__reference_resolver.resolve_node(self.__ast_id, self.__cu_hash)
        assert isinstance(node, UserDefinedValueTypeDefinition)
        return node


class Module(ExpressionTypeAbc):
    __source_unit_id: int

    def __init__(self, type_identifier: StringReader):
        type_identifier.read("t_module_")

        match = NUMBER_RE.match(type_identifier.data)
        assert match is not None, f"{type_identifier} is not a valid module"
        self.__ast_id = AstNodeId(int(match.group("number")))
        type_identifier.read(match.group("number"))

        self.__source_unit_id = int(match.group("number"))
