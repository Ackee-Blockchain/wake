from __future__ import annotations

import re
import typing as typ
from abc import ABC, abstractmethod
from pathlib import Path

if typ.TYPE_CHECKING:
    from wake.ir.declarations.contract_definition import ContractDefinition
    from wake.ir.declarations.enum_definition import EnumDefinition
    from wake.ir.declarations.struct_definition import StructDefinition
    from wake.ir.declarations.user_defined_value_type_definition import (
        UserDefinedValueTypeDefinition,
    )

from wake.ir.ast import AstNodeId
from wake.ir.enums import DataLocation, FunctionTypeKind, MagicTypeKind, StateMutability
from wake.ir.reference_resolver import ReferenceResolver
from wake.utils.string import StringReader

NUMBER_RE = re.compile(r"^(?P<number>[0-9]+)")
HEX_RE = re.compile(r"^(?P<hex>[0-9a-fA-F]+)")
IDENTIFIER_RE = re.compile(r"^\$_(?P<identifier>[a-zA-Z\$_][a-zA-Z0-9\$_]*)_\$")


class TypeAbc(ABC):
    """
    Abstract base class for all types.
    """

    @classmethod
    def from_type_identifier(
        cls,
        type_identifier: StringReader,
        reference_resolver: ReferenceResolver,
        cu_hash: bytes,
    ) -> typ.Optional[TypeAbc]:
        if type_identifier.startswith("t_address"):
            return Address.from_type_identifier(
                type_identifier, reference_resolver, cu_hash
            )
        elif type_identifier.startswith("t_bool"):
            return Bool.from_type_identifier(
                type_identifier, reference_resolver, cu_hash
            )
        elif type_identifier.startswith("t_int"):
            return Int.from_type_identifier(
                type_identifier, reference_resolver, cu_hash
            )
        elif type_identifier.startswith("t_uint"):
            return UInt.from_type_identifier(
                type_identifier, reference_resolver, cu_hash
            )
        elif type_identifier.startswith("t_stringliteral_"):
            return StringLiteral.from_type_identifier(
                type_identifier, reference_resolver, cu_hash
            )
        elif type_identifier.startswith("t_string_"):
            return String.from_type_identifier(
                type_identifier, reference_resolver, cu_hash
            )
        elif type_identifier.startswith("t_bytes_"):
            return Bytes.from_type_identifier(
                type_identifier, reference_resolver, cu_hash
            )
        # must go after t_bytes_ !!
        elif type_identifier.startswith("t_bytes"):
            return FixedBytes.from_type_identifier(
                type_identifier, reference_resolver, cu_hash
            )
        elif type_identifier.startswith("t_function"):
            return Function.from_type_identifier(
                type_identifier, reference_resolver, cu_hash
            )
        elif type_identifier.startswith("t_tuple"):
            return Tuple.from_type_identifier(
                type_identifier, reference_resolver, cu_hash
            )
        elif type_identifier.startswith("t_type"):
            return Type.from_type_identifier(
                type_identifier, reference_resolver, cu_hash
            )
        elif type_identifier.startswith("t_rational"):
            return Rational.from_type_identifier(
                type_identifier, reference_resolver, cu_hash
            )
        elif type_identifier.startswith("t_modifier"):
            return Modifier.from_type_identifier(
                type_identifier, reference_resolver, cu_hash
            )
        elif type_identifier.startswith("t_array"):
            return Array.from_type_identifier(
                type_identifier, reference_resolver, cu_hash
            )
        elif type_identifier.startswith("t_mapping"):
            return Mapping.from_type_identifier(
                type_identifier, reference_resolver, cu_hash
            )
        elif type_identifier.startswith("t_contract") or type_identifier.startswith(
            "t_super"
        ):
            return Contract.from_type_identifier(
                type_identifier, reference_resolver, cu_hash
            )
        elif type_identifier.startswith("t_struct"):
            return Struct.from_type_identifier(
                type_identifier, reference_resolver, cu_hash
            )
        elif type_identifier.startswith("t_enum"):
            return Enum.from_type_identifier(
                type_identifier, reference_resolver, cu_hash
            )
        elif type_identifier.startswith("t_magic"):
            return Magic.from_type_identifier(
                type_identifier, reference_resolver, cu_hash
            )
        elif type_identifier.startswith("t_userDefinedValueType"):
            return UserDefinedValueType.from_type_identifier(
                type_identifier, reference_resolver, cu_hash
            )
        elif type_identifier.startswith("t_module"):
            return Module.from_type_identifier(
                type_identifier, reference_resolver, cu_hash
            )
        elif type_identifier.startswith("t_fixed"):
            return Fixed.from_type_identifier(
                type_identifier, reference_resolver, cu_hash
            )
        elif type_identifier.startswith("t_ufixed"):
            return UFixed.from_type_identifier(
                type_identifier, reference_resolver, cu_hash
            )
        elif type_identifier.startswith("t_error"):
            return Error.from_type_identifier(
                type_identifier, reference_resolver, cu_hash
            )
        else:
            return None

    @property
    @abstractmethod
    def abi_type(self) -> str:
        """
        Raises:
            NotImplementedError: If the type cannot be represented in contract ABI.

        Returns:
            ABI type string.
        """
        ...


def _parse_list(
    type_identifier: StringReader, reference_resolver: ReferenceResolver, cu_hash: bytes
) -> typ.Tuple[typ.Optional[TypeAbc], ...]:
    type_identifier.read("$_")

    ret = []
    last_was_comma = False

    while True:
        while type_identifier.startswith("_$_"):
            type_identifier.read("_$_")
            if last_was_comma:
                ret.append(None)
            last_was_comma = True
        if type_identifier.startswith("_$"):
            break
        else:
            ret.append(
                TypeAbc.from_type_identifier(
                    type_identifier, reference_resolver, cu_hash
                )
            )
            last_was_comma = False
            if ret[-1] is None:
                # failed to parse => the last character was not a comma but a closing bracket
                type_identifier.insert("_$_")
                ret.pop()
                break

    type_identifier.read("_$")
    return tuple(ret)


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


class Address(TypeAbc):
    """
    Address type.
    """

    _is_payable: bool

    def __init__(self, is_payable: bool):
        self._is_payable = is_payable

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Address):
            return False
        return self._is_payable == other._is_payable

    def __hash__(self):
        return hash(self._is_payable)

    def __repr__(self):
        return f"Address(is_payable={self._is_payable})"

    @classmethod
    def from_type_identifier(
        cls,
        type_identifier: StringReader,
        reference_resolver: ReferenceResolver,
        cu_hash: bytes,
    ) -> Address:
        type_identifier.read("t_address")

        if type_identifier.startswith("_payable"):
            type_identifier.read("_payable")
            return Address(True)
        else:
            return Address(False)

    @property
    def abi_type(self) -> str:
        return "address"

    @property
    def is_payable(self) -> bool:
        """
        Returns:
            `True` if the address is payable, `False` otherwise.
        """
        return self._is_payable


class Bool(TypeAbc):
    """
    Boolean type.
    """

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Bool)

    def __hash__(self):
        return hash("bool")

    def __repr__(self):
        return "Bool()"

    @classmethod
    def from_type_identifier(
        cls,
        type_identifier: StringReader,
        reference_resolver: ReferenceResolver,
        cu_hash: bytes,
    ) -> Bool:
        type_identifier.read("t_bool")
        return Bool()

    @property
    def abi_type(self) -> str:
        return "bool"


class IntAbc(TypeAbc):
    """
    Base class for [Int][wake.ir.types.Int] and [UInt][wake.ir.types.UInt] types.
    """

    _bits_count: int

    @property
    def bits_count(self) -> int:
        """
        Can only be a multiple of 8, with a minimum of 8 and a maximum of 256.

        Returns:
            Number of bits used to represent this integer.
        """
        return self._bits_count


class Int(IntAbc):
    """
    Signed integer type.
    """

    def __init__(self, bits_count: int):
        self._bits_count = bits_count

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Int):
            return False
        return self._bits_count == other._bits_count

    def __hash__(self):
        return hash(self._bits_count)

    def __repr__(self):
        return f"Int(bits_count={self._bits_count})"

    @classmethod
    def from_type_identifier(
        cls,
        type_identifier: StringReader,
        reference_resolver: ReferenceResolver,
        cu_hash: bytes,
    ) -> Int:
        type_identifier.read("t_int")
        match = NUMBER_RE.match(type_identifier.data)
        assert match is not None
        number = match.group("number")
        type_identifier.read(number)
        return Int(int(number))

    @property
    def abi_type(self) -> str:
        return f"int{self._bits_count}"


class UInt(IntAbc):
    """
    Unsigned integer type.
    """

    def __init__(self, bits_count: int):
        self._bits_count = bits_count

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, UInt):
            return False
        return self._bits_count == other._bits_count

    def __hash__(self):
        return hash(self._bits_count)

    def __repr__(self):
        return f"UInt(bits_count={self._bits_count})"

    @classmethod
    def from_type_identifier(
        cls,
        type_identifier: StringReader,
        reference_resolver: ReferenceResolver,
        cu_hash: bytes,
    ) -> UInt:
        type_identifier.read("t_uint")
        match = NUMBER_RE.match(type_identifier.data)
        assert match is not None
        number = match.group("number")
        type_identifier.read(number)
        return UInt(int(number))

    @property
    def abi_type(self) -> str:
        return f"uint{self._bits_count}"


class FixedAbc(TypeAbc):
    """
    Base class for [Fixed][wake.ir.types.Fixed] and [UFixed][wake.ir.types.UFixed] types.
    !!! info
        Currently not fully implemented in Solidity.
    """

    _total_bits: int
    _fractional_digits: int

    @property
    def total_bits(self) -> int:
        """
        Returns:
            Total number of bits used to represent this fixed point number.
        """
        return self._total_bits

    @property
    def fractional_digits(self) -> int:
        """
        Returns:
            Number of decimal places available.
        """
        return self._fractional_digits


class Fixed(FixedAbc):
    """
    Signed fixed-point number type as specified by the [Solidity docs](https://docs.soliditylang.org/en/latest/types.html?highlight=fixed#fixed-point-numbers).
    !!! info
        Currently not fully implemented in Solidity.
    """

    def __init__(self, total_bits: int, fractional_digits: int):
        self._total_bits = total_bits
        self._fractional_digits = fractional_digits

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Fixed):
            return False
        return (
            self._total_bits == other._total_bits
            and self._fractional_digits == other._fractional_digits
        )

    def __hash__(self):
        return hash((self._total_bits, self._fractional_digits))

    def __repr__(self):
        return f"Fixed(total_bits={self._total_bits}, fractional_digits={self._fractional_digits})"

    @classmethod
    def from_type_identifier(
        cls,
        type_identifier: StringReader,
        reference_resolver: ReferenceResolver,
        cu_hash: bytes,
    ) -> Fixed:
        type_identifier.read("t_fixed")
        match = NUMBER_RE.match(type_identifier.data)
        assert match is not None
        total_bits = match.group("number")
        type_identifier.read(total_bits)

        type_identifier.read("x")

        match = NUMBER_RE.match(type_identifier.data)
        assert match is not None
        fractional_digits = match.group("number")
        type_identifier.read(fractional_digits)
        return Fixed(int(total_bits), int(fractional_digits))

    @property
    def abi_type(self) -> str:
        return f"fixed{self._total_bits}x{self._fractional_digits}"


class UFixed(FixedAbc):
    """
    Unsigned fixed point number type as specified by the [Solidity docs](https://docs.soliditylang.org/en/latest/types.html?highlight=ufixed#fixed-point-numbers).
    !!! info
        Currently not fully implemented in Solidity.
    """

    def __init__(self, total_bits: int, fractional_digits: int):
        self._total_bits = total_bits
        self._fractional_digits = fractional_digits

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, UFixed):
            return False
        return (
            self._total_bits == other._total_bits
            and self._fractional_digits == other._fractional_digits
        )

    def __hash__(self):
        return hash((self._total_bits, self._fractional_digits))

    def __repr__(self):
        return f"UFixed(total_bits={self._total_bits}, fractional_digits={self._fractional_digits})"

    @classmethod
    def from_type_identifier(
        cls,
        type_identifier: StringReader,
        reference_resolver: ReferenceResolver,
        cu_hash: bytes,
    ) -> UFixed:
        type_identifier.read("t_ufixed")
        match = NUMBER_RE.match(type_identifier.data)
        assert match is not None
        total_bits = match.group("number")
        type_identifier.read(total_bits)

        type_identifier.read("x")

        match = NUMBER_RE.match(type_identifier.data)
        assert match is not None
        fractional_digits = match.group("number")
        type_identifier.read(fractional_digits)
        return UFixed(int(total_bits), int(fractional_digits))

    @property
    def abi_type(self) -> str:
        return f"ufixed{self._total_bits}x{self._fractional_digits}"


class StringLiteral(TypeAbc):
    """
    String literal type.
    !!! warning
        This expression is of the [StringLiteral][wake.ir.types.StringLiteral] type:
        ```solidity
        "Hello, world!"
        ```

        However, this expression is of the [String][wake.ir.types.String] type and contains a child expression of the [StringLiteral][wake.ir.types.StringLiteral] type:
        ```solidity
        string("Hello, world!")
        ```
    """

    _keccak256_hash: bytes

    def __init__(self, keccak256_hash: bytes):
        self._keccak256_hash = keccak256_hash

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, StringLiteral):
            return False
        return self._keccak256_hash == other._keccak256_hash

    def __hash__(self):
        return hash(self._keccak256_hash)

    def __repr__(self):
        return f'StringLiteral(keccak256_hash=b"{self._keccak256_hash}"'

    @classmethod
    def from_type_identifier(
        cls,
        type_identifier: StringReader,
        reference_resolver: ReferenceResolver,
        cu_hash: bytes,
    ) -> StringLiteral:
        type_identifier.read("t_stringliteral_")
        match = HEX_RE.match(type_identifier.data)
        assert match is not None
        hex = match.group("hex")
        type_identifier.read(hex)
        return StringLiteral(bytes.fromhex(hex))

    @property
    def abi_type(self) -> str:
        raise NotImplementedError

    @property
    def keccak256_hash(self) -> bytes:
        """
        Returns:
            Keccak256 hash of the string literal.
        """
        return self._keccak256_hash


class String(TypeAbc):
    """
    String type.
    """

    _data_location: DataLocation
    _is_pointer: bool
    _is_slice: bool

    def __init__(self, data_location: DataLocation, is_pointer: bool, is_slice: bool):
        self._data_location = data_location
        self._is_pointer = is_pointer
        self._is_slice = is_slice

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, String):
            return False
        return (
            self._data_location == other._data_location
            and self._is_pointer == other._is_pointer
            and self._is_slice == other._is_slice
        )

    def __hash__(self):
        return hash((self._data_location, self._is_pointer, self._is_slice))

    def __repr__(self):
        return f"String(data_location={self._data_location}, is_pointer={self._is_pointer}, is_slice={self._is_slice})"

    @classmethod
    def from_type_identifier(
        cls,
        type_identifier: StringReader,
        reference_resolver: ReferenceResolver,
        cu_hash: bytes,
    ) -> String:
        type_identifier.read("t_string")
        if type_identifier.startswith("_storage"):
            data_location = DataLocation.STORAGE
            type_identifier.read("_storage")
        elif type_identifier.startswith("_memory"):
            data_location = DataLocation.MEMORY
            type_identifier.read("_memory")
        elif type_identifier.startswith("_calldata"):
            data_location = DataLocation.CALLDATA
            type_identifier.read("_calldata")
        else:
            assert False, f"Unexpected string type data location {type_identifier}"

        if type_identifier.startswith("_ptr"):
            is_pointer = True
            type_identifier.read("_ptr")
        else:
            is_pointer = False

        if type_identifier.startswith("_slice"):
            is_slice = True
            type_identifier.read("_slice")
        else:
            is_slice = False

        return String(data_location, is_pointer, is_slice)

    @property
    def abi_type(self) -> str:
        return "string"

    @property
    def data_location(self) -> DataLocation:
        """
        Can be either [CALLDATA][wake.ir.enums.DataLocation.CALLDATA], [MEMORY][wake.ir.enums.DataLocation.MEMORY] or [STORAGE][wake.ir.enums.DataLocation.STORAGE]

        Returns:
            Data location of the string expression.
        """
        return self._data_location

    @property
    def is_pointer(self) -> bool:
        """
        Storage references can be pointers or bound references. In general, local variables are of
        pointer type, state variables are bound references. Assignments to pointers or deleting
        them will not modify storage (that will only change the pointer). Assignment from
        non-storage objects to a variable of storage pointer type is not possible.

        For anything other than [STORAGE][wake.ir.enums.DataLocation.STORAGE], this always returns `True` because assignments
        never change the contents of the original value.

        Returns:
            Whether the string expression is a pointer to storage.
        """
        return self._is_pointer

    @property
    def is_slice(self) -> bool:
        """
        !!! example
            ```solidity
            function foo(string calldata s) public pure {
                s[0:5]; // s[0:5] is a string slice
            }
            ```

        Returns:
            Whether this is a slice of a string expression.
        """
        return self._is_slice


class Bytes(TypeAbc):
    """
    Bytes type.
    """

    _data_location: DataLocation
    _is_pointer: bool
    _is_slice: bool

    def __init__(self, data_location: DataLocation, is_pointer: bool, is_slice: bool):
        self._data_location = data_location
        self._is_pointer = is_pointer
        self._is_slice = is_slice

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Bytes):
            return False
        return (
            self._data_location == other._data_location
            and self._is_pointer == other._is_pointer
            and self._is_slice == other._is_slice
        )

    def __hash__(self):
        return hash((self._data_location, self._is_pointer, self._is_slice))

    def __repr__(self):
        return f"Bytes(data_location={self._data_location}, is_pointer={self._is_pointer}, is_slice={self._is_slice})"

    @classmethod
    def from_type_identifier(
        cls,
        type_identifier: StringReader,
        reference_resolver: ReferenceResolver,
        cu_hash: bytes,
    ) -> Bytes:
        type_identifier.read("t_bytes")
        if type_identifier.startswith("_storage"):
            data_location = DataLocation.STORAGE
            type_identifier.read("_storage")
        elif type_identifier.startswith("_memory"):
            data_location = DataLocation.MEMORY
            type_identifier.read("_memory")
        elif type_identifier.startswith("_calldata"):
            data_location = DataLocation.CALLDATA
            type_identifier.read("_calldata")
        else:
            assert False, f"Unexpected string type data location {type_identifier}"

        if type_identifier.startswith("_ptr"):
            is_pointer = True
            type_identifier.read("_ptr")
        else:
            is_pointer = False

        if type_identifier.startswith("_slice"):
            is_slice = True
            type_identifier.read("_slice")
        else:
            is_slice = False

        return Bytes(data_location, is_pointer, is_slice)

    @property
    def abi_type(self) -> str:
        return "bytes"

    @property
    def data_location(self) -> DataLocation:
        """
        Can be either [CALLDATA][wake.ir.enums.DataLocation.CALLDATA], [MEMORY][wake.ir.enums.DataLocation.MEMORY] or [STORAGE][wake.ir.enums.DataLocation.STORAGE]

        Returns:
            Data location of the bytes expression.
        """
        return self._data_location

    @property
    def is_pointer(self) -> bool:
        """
        Storage references can be pointers or bound references. In general, local variables are of
        pointer type, state variables are bound references. Assignments to pointers or deleting
        them will not modify storage (that will only change the pointer). Assignment from
        non-storage objects to a variable of storage pointer type is not possible.

        For anything other than [STORAGE][wake.ir.enums.DataLocation.STORAGE], this always returns `True` because assignments
        never change the contents of the original value.

        Returns:
            Whether the bytes expression is a pointer to storage.
        """
        return self._is_pointer

    @property
    def is_slice(self) -> bool:
        """
        !!! example
            ```solidity
            function foo(bytes calldata b) public pure {
                b[0:5]; // s[0:5] is a bytes slice
            }
            ```

        Returns:
            Whether this is a slice of a bytes expression.
        """
        return self._is_slice


class FixedBytes(TypeAbc):
    """
    Fixed-size byte array type.
    """

    _bytes_count: int

    def __init__(self, bytes_count: int):
        self._bytes_count = bytes_count

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, FixedBytes):
            return False
        return self._bytes_count == other._bytes_count

    def __hash__(self):
        return hash(self._bytes_count)

    def __repr__(self):
        return f"FixedBytes(bytes_count={self._bytes_count})"

    @classmethod
    def from_type_identifier(
        cls,
        type_identifier: StringReader,
        reference_resolver: ReferenceResolver,
        cu_hash: bytes,
    ) -> FixedBytes:
        type_identifier.read("t_bytes")
        match = NUMBER_RE.match(type_identifier.data)
        assert match is not None
        number = match.group("number")
        type_identifier.read(number)
        return FixedBytes(int(number))

    @property
    def abi_type(self) -> str:
        return f"bytes{self._bytes_count}"

    @property
    def bytes_count(self) -> int:
        """
        Is at least 1 and at most 32.

        Returns:
            Number of bytes used to represent this fixed-size byte array.
        """
        return self._bytes_count


class Function(TypeAbc):
    """
    Function type.

    !!! warning
        Given the following function:
        ```solidity
        function foo(uint a, uint b) public pure returns(uint, uint) {
            return (a + b, a - b);
        }
        ```
        and the following call:
        ```solidity
        foo(1, 2);
        ```
        the type of `foo` is [Function][wake.ir.types.Function], but the type of `:::solidity foo(1, 2)` is [Tuple][wake.ir.types.Tuple].
    """

    _kind: FunctionTypeKind
    _state_mutability: StateMutability
    _parameters: typ.Tuple[TypeAbc, ...]
    _return_parameters: typ.Tuple[TypeAbc, ...]
    _gas_set: bool
    _value_set: bool
    _salt_set: bool
    _attached_to: typ.Optional[typ.Tuple[TypeAbc, ...]]

    def __init__(
        self,
        kind: FunctionTypeKind,
        state_mutability: StateMutability,
        parameters: typ.Iterable[TypeAbc],
        return_parameters: typ.Iterable[TypeAbc],
        gas_set: bool,
        value_set: bool,
        salt_set: bool,
        attached_to: typ.Optional[typ.Iterable[TypeAbc]],
    ):
        self._kind = kind
        self._state_mutability = state_mutability
        self._parameters = tuple(parameters)
        self._return_parameters = tuple(return_parameters)
        self._gas_set = gas_set
        self._value_set = value_set
        self._salt_set = salt_set
        if attached_to is not None:
            self._attached_to = tuple(attached_to)
        else:
            self._attached_to = None

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Function):
            return False
        return (
            self._kind == other._kind
            and self._state_mutability == other._state_mutability
            and self._parameters == other._parameters
            and self._return_parameters == other._return_parameters
            and self._gas_set == other._gas_set
            and self._value_set == other._value_set
            and self._salt_set == other._salt_set
            and self._attached_to == other._attached_to
        )

    def __hash__(self):
        return hash(
            (
                self._kind,
                self._state_mutability,
                self._parameters,
                self._return_parameters,
                self._gas_set,
                self._value_set,
                self._salt_set,
                self._attached_to,
            )
        )

    def __repr__(self):
        return f"Function(kind={self._kind}, state_mutability={self._state_mutability}, parameters={self._parameters}, return_parameters={self._return_parameters}, gas_set={self._gas_set}, value_set={self._value_set}, salt_set={self._salt_set}, attached_to={self._attached_to})"

    @classmethod
    def from_type_identifier(
        cls,
        type_identifier: StringReader,
        reference_resolver: ReferenceResolver,
        cu_hash: bytes,
    ) -> Function:
        type_identifier.read("t_function_")

        matched = []
        for kind in FunctionTypeKind:
            if type_identifier.startswith(kind):
                matched.append(kind)
        assert len(matched) >= 1, f"Unexpected function kind {type_identifier}"
        kind = FunctionTypeKind(max(matched, key=len))
        type_identifier.read(kind)

        if type_identifier.startswith("_payable"):
            state_mutability = StateMutability.PAYABLE
            type_identifier.read("_payable")
        elif type_identifier.startswith("_pure"):
            state_mutability = StateMutability.PURE
            type_identifier.read("_pure")
        elif type_identifier.startswith("_nonpayable"):
            state_mutability = StateMutability.NONPAYABLE
            type_identifier.read("_nonpayable")
        elif type_identifier.startswith("_view"):
            state_mutability = StateMutability.VIEW
            type_identifier.read("_view")
        else:
            assert False, f"Unexpected function state mutability {type_identifier}"

        parameters = _parse_list(type_identifier, reference_resolver, cu_hash)
        assert not any(param is None for param in parameters)

        type_identifier.read("returns")
        return_parameters = _parse_list(type_identifier, reference_resolver, cu_hash)
        assert not any(param is None for param in return_parameters)

        if type_identifier.startswith("gas"):
            gas_set = True
            type_identifier.read("gas")
        else:
            gas_set = False

        if type_identifier.startswith("value"):
            value_set = True
            type_identifier.read("value")
        else:
            value_set = False

        if type_identifier.startswith("salt"):
            salt_set = True
            type_identifier.read("salt")
        else:
            salt_set = False

        if type_identifier.startswith("bound_to"):
            type_identifier.read("bound_to")
            bound_to = _parse_list(type_identifier, reference_resolver, cu_hash)
            assert not any(param is None for param in bound_to)
            attached_to = bound_to
        elif type_identifier.startswith(
            "attached_to"
        ):  # bound_to was renamed to attached_to in 0.8.18
            type_identifier.read("attached_to")
            attached_to = _parse_list(type_identifier, reference_resolver, cu_hash)
            assert not any(param is None for param in attached_to)
        else:
            attached_to = None

        return Function(
            kind,
            state_mutability,
            parameters,  # pyright: ignore reportArgumentType
            return_parameters,  # pyright: ignore reportArgumentType
            gas_set,
            value_set,
            salt_set,
            attached_to,  # pyright: ignore reportArgumentType
        )

    @property
    def abi_type(self) -> str:
        return "function"

    @property
    def kind(self) -> FunctionTypeKind:
        """
        Returns:
            Kind of the function type.
        """
        return self._kind

    @property
    def state_mutability(self) -> StateMutability:
        """
        Returns:
            State mutability of the function type.
        """
        return self._state_mutability

    @property
    def parameters(self) -> typ.Tuple[TypeAbc, ...]:
        """
        Returns:
            Expression types of the parameters of the function type.
        """
        return self._parameters

    @property
    def return_parameters(self) -> typ.Tuple[TypeAbc, ...]:
        """
        Returns:
            Expression types of the return parameters of the function type.
        """
        return self._return_parameters

    @property
    def gas_set(self) -> bool:
        """
        !!! example
            In the case of the old syntax (deprecated), the `gas` [MemberAccess][wake.ir.expressions.member_access.MemberAccess] expression is of the [Function][wake.ir.types.Function] type which returns a [Function][wake.ir.types.Function] with `gas_set` set to `True`.
            ```solidity
            foo.gas(10)(1, 2);
            ```

            In the case of the new syntax, the `{gas: 10}` [FunctionCallOptions][wake.ir.expressions.function_call_options.FunctionCallOptions] expression is of the [Function][wake.ir.types.Function] type with `gas_set` set to `True`.
            ```solidity
            foo{gas: 10}(1, 2);
            ```

        Returns:
            `True` if the gas is set in the function type.
        """
        return self._gas_set

    @property
    def value_set(self) -> bool:
        """
        !!! example
            In the case of the old syntax (deprecated), the `value` [MemberAccess][wake.ir.expressions.member_access.MemberAccess] expression is of the [Function][wake.ir.types.Function] type which returns a [Function][wake.ir.types.Function] with `value_set` set to `True`.
            ```solidity
            foo.value(1)(1, 2);
            ```

            In the case of the new syntax, the `{value: 1}` [FunctionCallOptions][wake.ir.expressions.function_call_options.FunctionCallOptions] expression is of the [Function][wake.ir.types.Function] type with `value_set` set to `True`.
            ```solidity
            foo{value: 1}(1, 2);
            ```

        Returns:
            `True` if the value is set in the function type.
        """
        return self._value_set

    @property
    def salt_set(self) -> bool:
        """
        !!! example
            In the following example, the `{salt: salt}` [FunctionCallOptions][wake.ir.expressions.function_call_options.FunctionCallOptions] expression is of the [Function][wake.ir.types.Function] type with `salt_set` set to `True`.
            ```solidity
            new Foo{salt: salt}();
            ```

        Returns:
            `True` if the salt is set in the function type.
        """
        return self._salt_set

    @property
    def attached_to(self) -> typ.Optional[typ.Tuple[TypeAbc, ...]]:
        """
        A function type can be attached to a type using the [UsingForDirective][wake.ir.meta.using_for_directive.UsingForDirective] or internally in the case of a Solidity global symbol.
        !!! example
            In the following example, the `add` [MemberAccess][wake.ir.expressions.member_access.MemberAccess] expression on line 9 is of the [Function][wake.ir.types.Function] type and is attached to the [UInt][wake.ir.types.UInt] type.
            ```solidity linenums="1"
            function add(uint a, uint b) pure returns (uint) {
                return a + b;
            }

            using {add} for uint;

            contract Foo {
                function bar(uint x) public pure returns(uint) {
                    return x.add(1);
                }
            }
            ```

            In this example, the `push` [MemberAccess][wake.ir.expressions.member_access.MemberAccess] expression on line 9 is of the [Function][wake.ir.types.Function] type and is attached to the [Array][wake.ir.types.Array] type.
            ```solidity
            arr.push(1);
            ```

        Returns:
            Type to which the function is attached to.
        """
        return self._attached_to


class Tuple(TypeAbc):
    """
    Tuple type.
    """

    _components: typ.Tuple[typ.Optional[TypeAbc], ...]

    def __init__(self, components: typ.Iterable[typ.Optional[TypeAbc]]):
        self._components = tuple(components)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Tuple):
            return False
        return self._components == other._components

    def __hash__(self):
        return hash(self._components)

    def __repr__(self):
        return f"Tuple(components={self._components})"

    @classmethod
    def from_type_identifier(
        cls,
        type_identifier: StringReader,
        reference_resolver: ReferenceResolver,
        cu_hash: bytes,
    ) -> Tuple:
        type_identifier.read("t_tuple")
        components = _parse_list(type_identifier, reference_resolver, cu_hash)
        return Tuple(components)

    @property
    def abi_type(self) -> str:
        if any(component is None for component in self._components):
            raise NotImplementedError
        return (
            "("
            + ",".join(
                component.abi_type  # pyright: ignore reportOptionalMemberAccess
                for component in self._components
            )
            + ")"
        )

    @property
    def components(self) -> typ.Tuple[typ.Optional[TypeAbc], ...]:
        """
        A component type can be `None` in the case of a tuple with a missing component.
        !!! example
            In the following example, the `(success, )` expression is of the [Tuple][wake.ir.types.Tuple] type with the components of the type [Bool][wake.ir.types.Bool] and `None`.
            ```solidity
            bool success;
            (success, ) = address(addr).call{value: 1}("");
            ```

        Returns:
            Expression types of the components of the tuple type.
        """
        return self._components


class Type(TypeAbc):
    """
    Type type. As opposed to other types, this type describes the type of a type, not the type of an instance of a type.
    """

    _actual_type: TypeAbc

    def __init__(self, actual_type: TypeAbc):
        self._actual_type = actual_type

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Type):
            return False
        return self._actual_type == other._actual_type

    def __hash__(self):
        return hash(self._actual_type)

    def __repr__(self):
        return f"Type(actual_type={self._actual_type})"

    @classmethod
    def from_type_identifier(
        cls,
        type_identifier: StringReader,
        reference_resolver: ReferenceResolver,
        cu_hash: bytes,
    ) -> Type:
        type_identifier.read("t_type")
        actual_type = _parse_list(type_identifier, reference_resolver, cu_hash)
        assert len(actual_type) == 1 and actual_type[0] is not None
        return Type(actual_type[0])

    @property
    def abi_type(self) -> str:
        raise NotImplementedError

    @property
    def actual_type(self) -> TypeAbc:
        """
        !!! example
            `payable` in the following example is of the [Type][wake.ir.types.Type] type with the [Address][wake.ir.types.Address] actual type.
            ```solidity
            payable(addr);
            ```

            `super` in the following example is of the [Type][wake.ir.types.Type] type with the [Contract][wake.ir.types.Contract] actual type.
            ```solidity
            super.foo();
            ```

            `string` in the following example is of the [Type][wake.ir.types.Type] type with the [String][wake.ir.types.String] actual type.
            ```solidity
            string.concat("foo", "bar");
            ```

            `Foo` in the following example on line 4 is of the [Type][wake.ir.types.Type] type with the [Enum][wake.ir.types.Enum] actual type.
            ```solidity linenums="1"
            enum Foo { A, B }

            function bar() pure returns (Foo) {
                return Foo.A;
            }
            ```

        Returns:
            Actual type of the type type.
        """
        return self._actual_type


class Rational(TypeAbc):
    """
    Rational type. Represents the type of constants or expressions with constants.

    !!! example
        `:::solidity 1`, `:::solidity 0x1234`, `:::solidity 1e18`, `:::solidity 1 * 2 / 3` are all of the [Rational][wake.ir.types.Rational] type.
    """

    _numerator: int
    _denominator: int

    def __init__(self, numerator: int, denominator: int):
        self._numerator = numerator
        self._denominator = denominator

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Rational):
            return False
        return (
            self._numerator == other._numerator
            and self._denominator == other._denominator
        )

    def __hash__(self):
        return hash((self._numerator, self._denominator))

    def __repr__(self):
        return f"Rational(numerator={self._numerator}, denominator={self._denominator})"

    @classmethod
    def from_type_identifier(
        cls,
        type_identifier: StringReader,
        reference_resolver: ReferenceResolver,
        cu_hash: bytes,
    ) -> Rational:
        type_identifier.read("t_rational_")

        if type_identifier.startswith("minus_"):
            type_identifier.read("minus_")
            numerator = -1
        else:
            numerator = 1

        match = NUMBER_RE.match(type_identifier.data)
        assert match is not None, f"{type_identifier} is not a valid rational"
        number = match.group("number")
        type_identifier.read(number)
        numerator *= int(number)

        type_identifier.read("_by_")

        match = NUMBER_RE.match(type_identifier.data)
        assert match is not None, f"{type_identifier} is not a valid rational"
        number = match.group("number")
        type_identifier.read(number)
        denominator = int(number)
        return Rational(numerator, denominator)

    @property
    def abi_type(self) -> str:
        raise NotImplementedError

    @property
    def numerator(self) -> int:
        """
        If the rational is negative, the numerator will be negative.

        Returns:
            Numerator of the rational number.
        """
        return self._numerator

    @property
    def denominator(self) -> int:
        """
        Returns:
            Denominator of the rational number.
        """
        return self._denominator


class Modifier(TypeAbc):
    """
    Modifier type.
    """

    _parameters: typ.Tuple[TypeAbc, ...]

    def __init__(self, parameters: typ.Iterable[TypeAbc]):
        self._parameters = tuple(parameters)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Modifier):
            return False
        return self._parameters == other._parameters

    def __hash__(self):
        return hash(self._parameters)

    def __repr__(self):
        return f"Modifier(parameters={self._parameters})"

    @classmethod
    def from_type_identifier(
        cls,
        type_identifier: StringReader,
        reference_resolver: ReferenceResolver,
        cu_hash: bytes,
    ) -> Modifier:
        type_identifier.read("t_modifier")
        parameters = _parse_list(type_identifier, reference_resolver, cu_hash)
        assert not any(param is None for param in parameters)
        return Modifier(parameters)  # pyright: ignore reportArgumentType

    @property
    def abi_type(self) -> str:
        raise NotImplementedError

    @property
    def parameters(self) -> typ.Tuple[TypeAbc, ...]:
        """
        Returns:
            Expression types of the parameters of the modifier.
        """
        return self._parameters


class Array(TypeAbc):
    """
    Array type.
    """

    _base_type: TypeAbc
    _length: typ.Optional[int]
    _data_location: DataLocation
    _is_pointer: bool
    _is_slice: bool

    def __init__(
        self,
        base_type: TypeAbc,
        length: typ.Optional[int],
        data_location: DataLocation,
        is_pointer: bool,
        is_slice: bool,
    ):
        self._base_type = base_type
        self._length = length
        self._data_location = data_location
        self._is_pointer = is_pointer
        self._is_slice = is_slice

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Array):
            return False
        return (
            self._base_type == other._base_type
            and self._length == other._length
            and self._data_location == other._data_location
            and self._is_pointer == other._is_pointer
            and self._is_slice == other._is_slice
        )

    def __hash__(self):
        return hash(
            (
                self._base_type,
                self._length,
                self._data_location,
                self._is_pointer,
                self._is_slice,
            )
        )

    def __repr__(self):
        return f"Array(base_type={self._base_type}, length={self._length}, data_location={self._data_location}, is_pointer={self._is_pointer}, is_slice={self._is_slice})"

    @classmethod
    def from_type_identifier(
        cls,
        type_identifier: StringReader,
        reference_resolver: ReferenceResolver,
        cu_hash: bytes,
    ) -> Array:
        type_identifier.read("t_array")
        base_type = _parse_list(type_identifier, reference_resolver, cu_hash)
        assert (
            len(base_type) == 1 and base_type[0] is not None
        ), f"Unexpected array base type {type_identifier}"
        base_type = base_type[0]

        if type_identifier.startswith("dyn"):
            length = None
            type_identifier.read("dyn")
        else:
            match = NUMBER_RE.match(type_identifier.data)
            assert match is not None, f"{type_identifier} is not a valid array length"
            length = int(match.group("number"))
            type_identifier.read(match.group("number"))

        if type_identifier.startswith("_storage"):
            data_location = DataLocation.STORAGE
            type_identifier.read("_storage")
        elif type_identifier.startswith("_memory"):
            data_location = DataLocation.MEMORY
            type_identifier.read("_memory")
        elif type_identifier.startswith("_calldata"):
            data_location = DataLocation.CALLDATA
            type_identifier.read("_calldata")
        else:
            assert False, f"Unexpected array type data location {type_identifier}"

        if type_identifier.startswith("_ptr"):
            is_pointer = True
            type_identifier.read("_ptr")
        else:
            is_pointer = False

        if type_identifier.startswith("_slice"):
            is_slice = True
            type_identifier.read("_slice")
        else:
            is_slice = False

        return Array(base_type, length, data_location, is_pointer, is_slice)

    @property
    def abi_type(self) -> str:
        if self.length is not None:
            return f"{self.base_type.abi_type}[{self.length}]"
        else:
            return f"{self.base_type.abi_type}[]"

    @property
    def base_type(self) -> TypeAbc:
        """
        Returns:
            Base type of the array.
        """
        return self._base_type

    @property
    def length(self) -> typ.Optional[int]:
        """
        Returns:
            Length of the array. `None` if the array is dynamic (not fixed size).
        """
        return self._length

    @property
    def data_location(self) -> DataLocation:
        """
        Returns:
            Data location of the array.
        """
        return self._data_location

    @property
    def is_pointer(self) -> bool:
        """
        Storage references can be pointers or bound references. In general, local variables are of
        pointer type, state variables are bound references. Assignments to pointers or deleting
        them will not modify storage (that will only change the pointer). Assignment from
        non-storage objects to a variable of storage pointer type is not possible.

        For anything other than [STORAGE][wake.ir.enums.DataLocation.STORAGE], this always returns `True` because assignments
        never change the contents of the original value.

        Returns:
            Whether the array expression is a pointer to storage.
        """
        return self._is_pointer

    @property
    def is_slice(self) -> bool:
        """
        !!! example
            ```solidity
            function foo(uint[] calldata arr) public pure {
                arr[0:5]; // arr[0:5] is an array slice
            }
            ```

        Returns:
            Whether this is a slice of an array expression.
        """
        return self._is_slice


class Mapping(TypeAbc):
    """
    Mapping type.
    """

    _key_type: TypeAbc
    _value_type: TypeAbc

    def __init__(self, key_type: TypeAbc, value_type: TypeAbc):
        self._key_type = key_type
        self._value_type = value_type

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Mapping):
            return False
        return (
            self._key_type == other._key_type and self._value_type == other._value_type
        )

    def __hash__(self):
        return hash((self._key_type, self._value_type))

    def __repr__(self):
        return f"Mapping(key_type={self._key_type}, value_type={self._value_type})"

    @classmethod
    def from_type_identifier(
        cls,
        type_identifier: StringReader,
        reference_resolver: ReferenceResolver,
        cu_hash: bytes,
    ) -> Mapping:
        type_identifier.read("t_mapping")
        key_value = _parse_list(type_identifier, reference_resolver, cu_hash)
        assert len(key_value) == 2, f"{type_identifier} is not a valid mapping"
        assert key_value[0] is not None, f"{type_identifier} is not a valid mapping"
        assert key_value[1] is not None, f"{type_identifier} is not a valid mapping"
        return Mapping(key_value[0], key_value[1])

    @property
    def abi_type(self) -> str:
        raise NotImplementedError

    @property
    def key_type(self) -> TypeAbc:
        """
        Returns:
            Key type of the mapping.
        """
        return self._key_type

    @property
    def value_type(self) -> TypeAbc:
        """
        Returns:
            Value type of the mapping.
        """
        return self._value_type


class Contract(TypeAbc):
    _is_super: bool
    _name: str
    _ast_id: AstNodeId
    _reference_resolver: ReferenceResolver
    _cu_hash: bytes

    def __init__(
        self,
        is_super: bool,
        name: str,
        ast_id: AstNodeId,
        reference_resolver: ReferenceResolver,
        cu_hash: bytes,
    ):
        self._is_super = is_super
        self._name = name
        self._ast_id = ast_id
        self._reference_resolver = reference_resolver
        self._cu_hash = cu_hash

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Contract):
            return False
        return (
            self._is_super == other._is_super
            and self._name == other._name
            and self.ir_node == other.ir_node
        )

    def __hash__(self):
        return hash((self._is_super, self._name, self.ir_node))

    def __repr__(self):
        return f"Contract(is_super={self._is_super}, name={self._name}, ir_node={self.ir_node})"

    @classmethod
    def from_type_identifier(
        cls,
        type_identifier: StringReader,
        reference_resolver: ReferenceResolver,
        cu_hash: bytes,
    ) -> Contract:
        if type_identifier.startswith("t_contract"):
            is_super = False
            type_identifier.read("t_contract")
        elif type_identifier.startswith("t_super"):
            is_super = True
            type_identifier.read("t_super")
        else:
            assert False, f"Unexpected contract type {type_identifier}"
        name = _parse_user_identifier(type_identifier)

        match = NUMBER_RE.match(type_identifier.data)
        assert match is not None, f"{type_identifier} is not a valid contract"
        ast_id = AstNodeId(int(match.group("number")))
        type_identifier.read(match.group("number"))

        return Contract(is_super, name, ast_id, reference_resolver, cu_hash)

    @property
    def abi_type(self) -> str:
        return "address"

    @property
    def is_super(self) -> bool:
        """
        !!! warning
            Until 0.7.6, the `super` keyword ([Identifier][wake.ir.expressions.identifier.Identifier]) was of the [Contract][wake.ir.types.Contract] type with `is_super` set to `True`.
            Since 0.8.0, the `super` keyword is of the [Type][wake.ir.types.Type] type with [Contract][wake.ir.types.Contract] as the `actual_type` and `is_super` set to `True`.

        !!! warning
            When this is `True`, the `name` and `ir_node` properties refer to the current contract, not the base contract.

        !!! example
            The `name` and `ir_node` properties of the [Contract][wake.ir.types.Contract] type of the `super` expression in the following example refer to the `Foo` contract, not the `Bar` contract.
            ```solidity
            contract Foo is Bar {
                function foo() public {
                    super.foo();
                }
            }
            ```

        Returns:
            `True` if the expression is the `super` keyword.
        """
        return self._is_super

    @property
    def name(self) -> str:
        """
        Returns:
            Name of the contract.
        """
        return self._name

    @property
    def ir_node(self) -> ContractDefinition:
        """
        Returns:
            Contract definition IR node.
        """
        from wake.ir.declarations.contract_definition import ContractDefinition

        node = self._reference_resolver.resolve_node(self._ast_id, self._cu_hash)
        assert isinstance(node, ContractDefinition)
        return node


class Struct(TypeAbc):
    """
    Struct type.
    """

    _name: str
    _ast_id: AstNodeId
    _data_location: DataLocation
    _is_pointer: bool
    _reference_resolver: ReferenceResolver
    _cu_hash: bytes

    def __init__(
        self,
        name: str,
        data_location: DataLocation,
        is_pointer: bool,
        ast_id: AstNodeId,
        reference_resolver: ReferenceResolver,
        cu_hash: bytes,
    ):
        self._name = name
        self._data_location = data_location
        self._is_pointer = is_pointer
        self._ast_id = ast_id
        self._reference_resolver = reference_resolver
        self._cu_hash = cu_hash

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Struct):
            return False
        return (
            self._name == other._name
            and self._data_location == other._data_location
            and self._is_pointer == other._is_pointer
            and self.ir_node == other.ir_node
        )

    def __hash__(self):
        return hash(
            (
                self._name,
                self._data_location,
                self._is_pointer,
                self.ir_node,
            )
        )

    def __repr__(self):
        return f"Struct(name={self._name}, data_location={self._data_location}, is_pointer={self._is_pointer}, ir_node={self.ir_node})"

    @classmethod
    def from_type_identifier(
        cls,
        type_identifier: StringReader,
        reference_resolver: ReferenceResolver,
        cu_hash: bytes,
    ) -> Struct:
        type_identifier.read("t_struct")
        name = _parse_user_identifier(type_identifier)

        match = NUMBER_RE.match(type_identifier.data)
        assert match is not None, f"{type_identifier} is not a valid struct"
        ast_id = AstNodeId(int(match.group("number")))
        type_identifier.read(match.group("number"))

        if type_identifier.startswith("_storage"):
            data_location = DataLocation.STORAGE
            type_identifier.read("_storage")
        elif type_identifier.startswith("_memory"):
            data_location = DataLocation.MEMORY
            type_identifier.read("_memory")
        elif type_identifier.startswith("_calldata"):
            data_location = DataLocation.CALLDATA
            type_identifier.read("_calldata")
        else:
            assert False, f"Unexpected array type data location {type_identifier}"

        if type_identifier.startswith("_ptr"):
            is_pointer = True
            type_identifier.read("_ptr")
        else:
            is_pointer = False

        return Struct(
            name, data_location, is_pointer, ast_id, reference_resolver, cu_hash
        )

    @property
    def abi_type(self) -> str:
        return (
            "("
            + ",".join([member.type.abi_type for member in self.ir_node.members])
            + ")"
        )

    @property
    def name(self) -> str:
        """
        Returns:
            Name of the struct.
        """
        return self._name

    @property
    def data_location(self) -> DataLocation:
        """
        Returns:
            Data location of the struct.
        """
        return self._data_location

    @property
    def is_pointer(self) -> bool:
        """
        Storage references can be pointers or bound references. In general, local variables are of
        pointer type, state variables are bound references. Assignments to pointers or deleting
        them will not modify storage (that will only change the pointer). Assignment from
        non-storage objects to a variable of storage pointer type is not possible.

        For anything other than [STORAGE][wake.ir.enums.DataLocation.STORAGE], this always returns `True` because assignments
        never change the contents of the original value.

        Returns:
            Whether the struct expression is a pointer to storage.
        """
        return self._is_pointer

    @property
    def ir_node(self) -> StructDefinition:
        """
        Returns:
            Struct definition IR node.
        """
        from wake.ir.declarations.struct_definition import StructDefinition

        node = self._reference_resolver.resolve_node(self._ast_id, self._cu_hash)
        assert isinstance(node, StructDefinition)
        return node


class Enum(TypeAbc):
    """
    Enum type.

    !!! warning
        Enum values are of the [Enum][wake.ir.types.Enum] type and enums are of the [Type][wake.ir.types.Type] type with [Enum][wake.ir.types.Enum] as the [actual_type][wake.ir.types.Type.actual_type].
    """

    _name: str
    _ast_id: AstNodeId
    _reference_resolver: ReferenceResolver
    _cu_hash: bytes

    def __init__(
        self,
        name: str,
        ast_id: AstNodeId,
        reference_resolver: ReferenceResolver,
        cu_hash: bytes,
    ):
        self._name = name
        self._ast_id = ast_id
        self._reference_resolver = reference_resolver
        self._cu_hash = cu_hash

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Enum):
            return False
        return self._name == other._name and self.ir_node == other.ir_node

    def __hash__(self):
        return hash((self._name, self.ir_node))

    def __repr__(self):
        return f"Enum(name={self._name}, ir_node={self.ir_node})"

    @classmethod
    def from_type_identifier(
        cls,
        type_identifier: StringReader,
        reference_resolver: ReferenceResolver,
        cu_hash: bytes,
    ) -> Enum:
        type_identifier.read("t_enum")
        name = _parse_user_identifier(type_identifier)

        match = NUMBER_RE.match(type_identifier.data)
        assert match is not None, f"{type_identifier} is not a valid enum"
        ast_id = AstNodeId(int(match.group("number")))
        type_identifier.read(match.group("number"))

        return Enum(name, ast_id, reference_resolver, cu_hash)

    @property
    def abi_type(self) -> str:
        return "uint8"

    @property
    def name(self) -> str:
        """
        Returns:
            Name of the enum.
        """
        return self._name

    @property
    def ir_node(self) -> EnumDefinition:
        """
        Returns:
            Enum definition IR node.
        """
        from wake.ir.declarations.enum_definition import EnumDefinition

        node = self._reference_resolver.resolve_node(self._ast_id, self._cu_hash)
        assert isinstance(node, EnumDefinition)
        return node


class Magic(TypeAbc):
    """
    Magic type represents Solidity language built-in objects.
    """

    _kind: MagicTypeKind
    _meta_argument_type: typ.Optional[TypeAbc]

    def __init__(self, kind: MagicTypeKind, meta_argument_type: typ.Optional[TypeAbc]):
        self._kind = kind
        self._meta_argument_type = meta_argument_type

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Magic):
            return False
        return (
            self._kind == other._kind
            and self._meta_argument_type == other._meta_argument_type
        )

    def __hash__(self):
        return hash((self._kind, self._meta_argument_type))

    def __repr__(self):
        return (
            f"Magic(kind={self._kind}, meta_argument_type={self._meta_argument_type})"
        )

    @classmethod
    def from_type_identifier(
        cls,
        type_identifier: StringReader,
        reference_resolver: ReferenceResolver,
        cu_hash: bytes,
    ) -> Magic:
        type_identifier.read("t_magic_")

        for magic_kind in MagicTypeKind:
            if type_identifier.startswith(magic_kind):
                kind = MagicTypeKind(magic_kind)
                type_identifier.read(magic_kind)

                if kind == MagicTypeKind.META_TYPE:
                    type_identifier.read("_")
                    meta_argument_type = TypeAbc.from_type_identifier(
                        type_identifier, reference_resolver, cu_hash
                    )
                    assert meta_argument_type is not None
                    meta_argument_type = meta_argument_type
                else:
                    meta_argument_type = None

                return Magic(kind, meta_argument_type)

        assert False, f"Unexpected magic type {type_identifier}"

    @property
    def abi_type(self) -> str:
        raise NotImplementedError

    @property
    def kind(self) -> MagicTypeKind:
        """
        Returns:
            Kind of the magic type.
        """
        return self._kind

    @property
    def meta_argument_type(self) -> typ.Optional[TypeAbc]:
        """
        Is only set for [MagicTypeKind.META_TYPE][wake.ir.enums.MagicTypeKind.META_TYPE] kind.
        !!! example
            [Contract][wake.ir.types.Contract] in `:::solidity type(IERC20)`, [UInt][wake.ir.types.UInt] in `:::solidity type(uint)`.

        Returns:
            Type of the meta expression argument.
        """
        return self._meta_argument_type


class UserDefinedValueType(TypeAbc):
    _name: str
    _ast_id: AstNodeId
    _reference_resolver: ReferenceResolver
    _cu_hash: bytes

    def __init__(
        self,
        name: str,
        ast_id: AstNodeId,
        reference_resolver: ReferenceResolver,
        cu_hash: bytes,
    ):
        self._name = name
        self._ast_id = ast_id
        self._reference_resolver = reference_resolver
        self._cu_hash = cu_hash

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, UserDefinedValueType):
            return False
        return self._name == other._name and self.ir_node == other.ir_node

    def __hash__(self):
        return hash((self._name, self.ir_node))

    def __repr__(self):
        return f"UserDefinedValueType(name={self._name}, ir_node={self.ir_node})"

    @classmethod
    def from_type_identifier(
        cls,
        type_identifier: StringReader,
        reference_resolver: ReferenceResolver,
        cu_hash: bytes,
    ) -> UserDefinedValueType:
        type_identifier.read("t_userDefinedValueType")
        name = _parse_user_identifier(type_identifier)

        match = NUMBER_RE.match(type_identifier.data)
        assert match is not None, f"{type_identifier} is not a valid enum"
        ast_id = AstNodeId(int(match.group("number")))
        type_identifier.read(match.group("number"))

        return UserDefinedValueType(name, ast_id, reference_resolver, cu_hash)

    @property
    def abi_type(self) -> str:
        return self.ir_node.underlying_type.type.abi_type

    @property
    def name(self) -> str:
        """
        Returns:
            Name of the user defined value type.
        """
        return self._name

    @property
    def ir_node(self) -> UserDefinedValueTypeDefinition:
        """
        Returns:
            User defined value type definition IR node.
        """
        from wake.ir.declarations.user_defined_value_type_definition import (
            UserDefinedValueTypeDefinition,
        )

        node = self._reference_resolver.resolve_node(self._ast_id, self._cu_hash)
        assert isinstance(node, UserDefinedValueTypeDefinition)
        return node


class Module(TypeAbc):
    """
    Module type.
    !!! note
        It is probably currently not possible to create an expression of this type.
    """

    _source_unit_id: int
    _reference_resolver: ReferenceResolver
    _cu_hash: bytes

    def __init__(
        self, source_unit_id: int, reference_resolver: ReferenceResolver, cu_hash: bytes
    ):
        self._source_unit_id = source_unit_id
        self._reference_resolver = reference_resolver
        self._cu_hash = cu_hash

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Module):
            return False
        return self.file == other.file

    def __hash__(self):
        return hash(self.file)

    def __repr__(self):
        return f"Module(file={self.file})"

    @classmethod
    def from_type_identifier(
        cls,
        type_identifier: StringReader,
        reference_resolver: ReferenceResolver,
        cu_hash: bytes,
    ) -> Module:
        type_identifier.read("t_module_")

        match = NUMBER_RE.match(type_identifier.data)
        assert match is not None, f"{type_identifier} is not a valid module"
        source_unit_id = int(match.group("number"))
        type_identifier.read(match.group("number"))

        return Module(source_unit_id, reference_resolver, cu_hash)

    @property
    def abi_type(self) -> str:
        raise NotImplementedError

    @property
    def file(self) -> Path:
        """
        Returns:
            Path representing the source file (module).
        """
        return self._reference_resolver.resolve_source_file_id(
            self._source_unit_id, self._cu_hash
        )


class Error(TypeAbc):
    """
    Error type.
    """

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Error)

    def __hash__(self):
        return hash("Error")

    def __repr__(self):
        return "Error"

    @classmethod
    def from_type_identifier(
        cls,
        type_identifier: StringReader,
        reference_resolver: ReferenceResolver,
        cu_hash: bytes,
    ) -> Error:
        type_identifier.read("t_error")
        return Error()

    @property
    def abi_type(self) -> str:
        raise NotImplementedError
