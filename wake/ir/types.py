from __future__ import annotations

import re
import typing as typ
from abc import ABC, abstractmethod

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
    ) -> typ.Optional["TypeAbc"]:
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
            return Tuple(type_identifier, reference_resolver, cu_hash)
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

    __is_payable: bool

    def __init__(self, type_identifier: StringReader):
        type_identifier.read("t_address")

        if type_identifier.startswith("_payable"):
            type_identifier.read("_payable")
            self.__is_payable = True
        else:
            self.__is_payable = False

    @property
    def abi_type(self) -> str:
        return "address"

    @property
    def is_payable(self) -> bool:
        """
        Returns:
            `True` if the address is payable, `False` otherwise.
        """
        return self.__is_payable


class Bool(TypeAbc):
    """
    Boolean type.
    """

    def __init__(self, type_identifier: StringReader):
        type_identifier.read("t_bool")

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

    def __init__(self, type_identifier: StringReader):
        type_identifier.read("t_int")
        match = NUMBER_RE.match(type_identifier.data)
        assert match is not None
        number = match.group("number")
        type_identifier.read(number)
        self._bits_count = int(number)

    @property
    def abi_type(self) -> str:
        return f"int{self._bits_count}"


class UInt(IntAbc):
    """
    Unsigned integer type.
    """

    def __init__(self, type_identifier: StringReader):
        type_identifier.read("t_uint")
        match = NUMBER_RE.match(type_identifier.data)
        assert match is not None
        number = match.group("number")
        type_identifier.read(number)
        self._bits_count = int(number)

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

    def __init__(self, type_identifier: StringReader):
        type_identifier.read("t_fixed")
        match = NUMBER_RE.match(type_identifier.data)
        assert match is not None
        total_bits = match.group("number")
        type_identifier.read(total_bits)
        self._total_bits = int(total_bits)

        type_identifier.read("x")

        match = NUMBER_RE.match(type_identifier.data)
        assert match is not None
        fractional_digits = match.group("number")
        type_identifier.read(fractional_digits)
        self._fractional_digits = int(fractional_digits)

    @property
    def abi_type(self) -> str:
        raise NotImplementedError


class UFixed(FixedAbc):
    """
    Unsigned fixed point number type as specified by the [Solidity docs](https://docs.soliditylang.org/en/latest/types.html?highlight=ufixed#fixed-point-numbers).
    !!! info
        Currently not fully implemented in Solidity.
    """

    def __init__(self, type_identifier: StringReader):
        type_identifier.read("t_ufixed")
        match = NUMBER_RE.match(type_identifier.data)
        assert match is not None
        total_bits = match.group("number")
        type_identifier.read(total_bits)
        self._total_bits = int(total_bits)

        type_identifier.read("x")

        match = NUMBER_RE.match(type_identifier.data)
        assert match is not None
        fractional_digits = match.group("number")
        type_identifier.read(fractional_digits)
        self._fractional_digits = int(fractional_digits)

    @property
    def abi_type(self) -> str:
        raise NotImplementedError


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

    __keccak256_hash: bytes

    def __init__(self, type_identifier: StringReader):
        type_identifier.read("t_stringliteral_")
        match = HEX_RE.match(type_identifier.data)
        assert match is not None
        hex = match.group("hex")
        type_identifier.read(hex)
        self.__keccak256_hash = bytes.fromhex(hex)

    @property
    def abi_type(self) -> str:
        raise NotImplementedError

    @property
    def keccak256_hash(self) -> bytes:
        """
        Returns:
            Keccak256 hash of the string literal.
        """
        return self.__keccak256_hash


class String(TypeAbc):
    """
    String type.
    """

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
    def abi_type(self) -> str:
        return "string"

    @property
    def data_location(self) -> DataLocation:
        """
        Can be either [CALLDATA][wake.ir.enums.DataLocation.CALLDATA], [MEMORY][wake.ir.enums.DataLocation.MEMORY] or [STORAGE][wake.ir.enums.DataLocation.STORAGE]

        Returns:
            Data location of the string expression.
        """
        return self.__data_location

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
        return self.__is_pointer

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
        return self.__is_slice


class Bytes(TypeAbc):
    """
    Bytes type.
    """

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
    def abi_type(self) -> str:
        return "bytes"

    @property
    def data_location(self) -> DataLocation:
        """
        Can be either [CALLDATA][wake.ir.enums.DataLocation.CALLDATA], [MEMORY][wake.ir.enums.DataLocation.MEMORY] or [STORAGE][wake.ir.enums.DataLocation.STORAGE]

        Returns:
            Data location of the bytes expression.
        """
        return self.__data_location

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
        return self.__is_pointer

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
        return self.__is_slice


class FixedBytes(TypeAbc):
    """
    Fixed-size byte array type.
    """

    __bytes_count: int

    def __init__(self, type_identifier: StringReader):
        type_identifier.read("t_bytes")
        match = NUMBER_RE.match(type_identifier.data)
        assert match is not None
        number = match.group("number")
        type_identifier.read(number)
        self.__bytes_count = int(number)

    @property
    def abi_type(self) -> str:
        return f"bytes{self.__bytes_count}"

    @property
    def bytes_count(self) -> int:
        """
        Is at least 1 and at most 32.

        Returns:
            Number of bytes used to represent this fixed-size byte array.
        """
        return self.__bytes_count


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

    __kind: FunctionTypeKind
    __state_mutability: StateMutability
    __parameters: typ.Tuple[TypeAbc, ...]
    __return_parameters: typ.Tuple[TypeAbc, ...]
    __gas_set: bool
    __value_set: bool
    __salt_set: bool
    __attached_to: typ.Optional[typ.Tuple[TypeAbc, ...]]

    def __init__(
        self,
        type_identifier: StringReader,
        reference_resolver: ReferenceResolver,
        cu_hash: bytes,
    ):
        type_identifier.read("t_function_")

        matched = []
        for kind in FunctionTypeKind:
            if type_identifier.startswith(kind):
                matched.append(kind)
        assert len(matched) >= 1, f"Unexpected function kind {type_identifier}"
        self.__kind = FunctionTypeKind(max(matched, key=len))
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
            self.__attached_to = bound_to  # type: ignore
        elif type_identifier.startswith(
            "attached_to"
        ):  # bound_to was renamed to attached_to in 0.8.18
            type_identifier.read("attached_to")
            attached_to = _parse_list(type_identifier, reference_resolver, cu_hash)
            assert not any(param is None for param in attached_to)
            self.__attached_to = attached_to  # type: ignore
        else:
            self.__attached_to = None

    @property
    def abi_type(self) -> str:
        return "function"

    @property
    def kind(self) -> FunctionTypeKind:
        """
        Returns:
            Kind of the function type.
        """
        return self.__kind

    @property
    def state_mutability(self) -> StateMutability:
        """
        Returns:
            State mutability of the function type.
        """
        return self.__state_mutability

    @property
    def parameters(self) -> typ.Tuple[TypeAbc, ...]:
        """
        Returns:
            Expression types of the parameters of the function type.
        """
        return self.__parameters

    @property
    def return_parameters(self) -> typ.Tuple[TypeAbc, ...]:
        """
        Returns:
            Expression types of the return parameters of the function type.
        """
        return self.__return_parameters

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
        return self.__gas_set

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
        return self.__value_set

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
        return self.__salt_set

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
        return self.__attached_to


class Tuple(TypeAbc):
    """
    Tuple type.
    """

    __components: typ.Tuple[typ.Optional[TypeAbc], ...]

    def __init__(
        self,
        type_identifier: StringReader,
        reference_resolver: ReferenceResolver,
        cu_hash: bytes,
    ):
        type_identifier.read("t_tuple")
        self.__components = _parse_list(type_identifier, reference_resolver, cu_hash)

    @property
    def abi_type(self) -> str:
        if any(component is None for component in self.__components):
            raise NotImplementedError
        return (
            "("
            + ",".join(
                component.abi_type  # pyright: ignore reportOptionalMemberAccess
                for component in self.__components
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
        return self.__components


class Type(TypeAbc):
    """
    Type type. As opposed to other types, this type describes the type of a type, not the type of an instance of a type.
    """

    __actual_type: TypeAbc

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
        return self.__actual_type


class Rational(TypeAbc):
    """
    Rational type. Represents the type of constants or expressions with constants.

    !!! example
        `:::solidity 1`, `:::solidity 0x1234`, `:::solidity 1e18`, `:::solidity 1 * 2 / 3` are all of the [Rational][wake.ir.types.Rational] type.
    """

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
    def abi_type(self) -> str:
        raise NotImplementedError

    @property
    def numerator(self) -> int:
        """
        If the rational is negative, the numerator will be negative.

        Returns:
            Numerator of the rational number.
        """
        return self.__numerator

    @property
    def denominator(self) -> int:
        """
        Returns:
            Denominator of the rational number.
        """
        return self.__denominator


class Modifier(TypeAbc):
    """
    Modifier type.
    """

    __parameters: typ.Tuple[TypeAbc, ...]

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
    def abi_type(self) -> str:
        raise NotImplementedError

    @property
    def parameters(self) -> typ.Tuple[TypeAbc, ...]:
        """
        Returns:
            Expression types of the parameters of the modifier.
        """
        return self.__parameters


class Array(TypeAbc):
    """
    Array type.
    """

    __base_type: TypeAbc
    __length: typ.Optional[int]
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
        return self.__base_type

    @property
    def length(self) -> typ.Optional[int]:
        """
        Returns:
            Length of the array. `None` if the array is dynamic (not fixed size).
        """
        return self.__length

    @property
    def data_location(self) -> DataLocation:
        """
        Returns:
            Data location of the array.
        """
        return self.__data_location

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
        return self.__is_pointer

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
        return self.__is_slice


class Mapping(TypeAbc):
    """
    Mapping type.
    """

    __key_type: TypeAbc
    __value_type: TypeAbc

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
    def abi_type(self) -> str:
        raise NotImplementedError

    @property
    def key_type(self) -> TypeAbc:
        """
        Returns:
            Key type of the mapping.
        """
        return self.__key_type

    @property
    def value_type(self) -> TypeAbc:
        """
        Returns:
            Value type of the mapping.
        """
        return self.__value_type


class Contract(TypeAbc):
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
        return self.__is_super

    @property
    def name(self) -> str:
        """
        Returns:
            Name of the contract.
        """
        return self.__name

    @property
    def ir_node(self) -> ContractDefinition:
        """
        Returns:
            Contract definition IR node.
        """
        from wake.ir.declarations.contract_definition import ContractDefinition

        node = self.__reference_resolver.resolve_node(self.__ast_id, self.__cu_hash)
        assert isinstance(node, ContractDefinition)
        return node


class Struct(TypeAbc):
    """
    Struct type.
    """

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
        return self.__name

    @property
    def data_location(self) -> DataLocation:
        """
        Returns:
            Data location of the struct.
        """
        return self.__data_location

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
        return self.__is_pointer

    @property
    def ir_node(self) -> StructDefinition:
        """
        Returns:
            Struct definition IR node.
        """
        from wake.ir.declarations.struct_definition import StructDefinition

        node = self.__reference_resolver.resolve_node(self.__ast_id, self.__cu_hash)
        assert isinstance(node, StructDefinition)
        return node


class Enum(TypeAbc):
    """
    Enum type.

    !!! warning
        Enum values are of the [Enum][wake.ir.types.Enum] type and enums are of the [Type][wake.ir.types.Type] type with [Enum][wake.ir.types.Enum] as the [actual_type][wake.ir.types.Type.actual_type].
    """

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
    def abi_type(self) -> str:
        return "uint8"

    @property
    def name(self) -> str:
        """
        Returns:
            Name of the enum.
        """
        return self.__name

    @property
    def ir_node(self) -> EnumDefinition:
        """
        Returns:
            Enum definition IR node.
        """
        from wake.ir.declarations.enum_definition import EnumDefinition

        node = self.__reference_resolver.resolve_node(self.__ast_id, self.__cu_hash)
        assert isinstance(node, EnumDefinition)
        return node


class Magic(TypeAbc):
    """
    Magic type represents Solidity language built-in objects.
    """

    __kind: MagicTypeKind
    __meta_argument_type: typ.Optional[TypeAbc]

    def __init__(
        self,
        type_identifier: StringReader,
        reference_resolver: ReferenceResolver,
        cu_hash: bytes,
    ):
        type_identifier.read("t_magic_")

        matched = False
        for kind in MagicTypeKind:
            if type_identifier.startswith(kind):
                self.__kind = MagicTypeKind(kind)
                type_identifier.read(kind)
                matched = True
                break
        assert matched, f"Unexpected magic kind {type_identifier}"

        if self.__kind == MagicTypeKind.META_TYPE:
            type_identifier.read("_")
            meta_argument_type = TypeAbc.from_type_identifier(
                type_identifier, reference_resolver, cu_hash
            )
            assert meta_argument_type is not None
            self.__meta_argument_type = meta_argument_type
        else:
            self.__meta_argument_type = None

    @property
    def abi_type(self) -> str:
        raise NotImplementedError

    @property
    def kind(self) -> MagicTypeKind:
        """
        Returns:
            Kind of the magic type.
        """
        return self.__kind

    @property
    def meta_argument_type(self) -> typ.Optional[TypeAbc]:
        """
        Is only set for [MagicTypeKind.META_TYPE][wake.ir.enums.MagicTypeKind.META_TYPE] kind.
        !!! example
            [Contract][wake.ir.types.Contract] in `:::solidity type(IERC20)`, [UInt][wake.ir.types.UInt] in `:::solidity type(uint)`.

        Returns:
            Type of the meta expression argument.
        """
        return self.__meta_argument_type


class UserDefinedValueType(TypeAbc):
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
    def abi_type(self) -> str:
        return self.ir_node.underlying_type.type.abi_type

    @property
    def name(self) -> str:
        """
        Returns:
            Name of the user defined value type.
        """
        return self.__name

    @property
    def ir_node(self) -> UserDefinedValueTypeDefinition:
        """
        Returns:
            User defined value type definition IR node.
        """
        from wake.ir.declarations.user_defined_value_type_definition import (
            UserDefinedValueTypeDefinition,
        )

        node = self.__reference_resolver.resolve_node(self.__ast_id, self.__cu_hash)
        assert isinstance(node, UserDefinedValueTypeDefinition)
        return node


class Module(TypeAbc):
    """
    Module type.
    !!! note
        It is probably currently not possible to create an expression of this type.
    """

    __source_unit_id: int

    def __init__(self, type_identifier: StringReader):
        type_identifier.read("t_module_")

        match = NUMBER_RE.match(type_identifier.data)
        assert match is not None, f"{type_identifier} is not a valid module"
        self.__ast_id = AstNodeId(int(match.group("number")))
        type_identifier.read(match.group("number"))

        self.__source_unit_id = int(match.group("number"))

    @property
    def abi_type(self) -> str:
        raise NotImplementedError
