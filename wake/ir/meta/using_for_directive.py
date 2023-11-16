from __future__ import annotations

from typing import TYPE_CHECKING, Iterator, List, Optional, Tuple, Union

from wake.ir.enums import BinaryOpOperator, UnaryOpOperator
from wake.ir.meta.identifier_path import IdentifierPath
from wake.ir.type_names.abc import TypeNameAbc
from wake.ir.type_names.user_defined_type_name import UserDefinedTypeName
from wake.ir.utils import IrInitTuple

if TYPE_CHECKING:
    from wake.ir.declarations.contract_definition import ContractDefinition
    from .source_unit import SourceUnit

from wake.ir.abc import IrAbc, SolidityAbc
from wake.ir.ast import (
    SolcIdentifierPath,
    SolcUserDefinedTypeName,
    SolcUsingForDirective,
)


class UsingForDirective(SolidityAbc):
    """
    !!! note
        Either [library_name][wake.ir.meta.using_for_directive.UsingForDirective.library_name] must be set or one of [functions][wake.ir.meta.using_for_directive.UsingForDirective.functions] or [operator_functions][wake.ir.meta.using_for_directive.UsingForDirective.operator_functions] must be non-empty.
    !!! example
        Lines 18, 21 and 22 in the following example:
        ```solidity linenums="1"
        type I8 is int8;

        function add(uint a, uint b) pure returns (uint) {
            return a + b;
        }

        function sub(I8 a, I8 b) pure returns (I8) {
            return I8.wrap(I8.unwrap(a) - I8.unwrap(b));
        }

        library SafeMath {
            function sub(uint a, uint b) public pure returns (uint) {
                require(b <= a);
                return a - b;
            }
        }

        using {sub as -} for I8 global;

        contract C {
            using SafeMath for uint;
            using {add} for uint;
        }
        ```
    """

    _ast_node: SolcUsingForDirective
    _parent: Union[ContractDefinition, SourceUnit]

    _functions: List[IdentifierPath]
    _operator_functions: List[
        Tuple[IdentifierPath, Union[UnaryOpOperator, BinaryOpOperator]]
    ]
    _library_name: Optional[Union[IdentifierPath, UserDefinedTypeName]]
    _type_name: Optional[TypeNameAbc]
    # TODO add _global

    def __init__(
        self,
        init: IrInitTuple,
        using_for_directive: SolcUsingForDirective,
        parent: Union[ContractDefinition, SourceUnit],
    ):
        super().__init__(init, using_for_directive, parent)

        if using_for_directive.function_list is None:
            self._functions = []
            self._operator_functions = []
        else:
            self._functions = [
                IdentifierPath(init, function.function, self)
                for function in using_for_directive.function_list
                if function.function is not None
            ]
            self._operator_functions = [
                (
                    IdentifierPath(init, function.definition, self),
                    function.operator,
                )
                for function in using_for_directive.function_list
                if function.definition is not None and function.operator is not None
            ]

        if using_for_directive.library_name is None:
            self._library_name = None
        elif isinstance(using_for_directive.library_name, SolcUserDefinedTypeName):
            self._library_name = UserDefinedTypeName(
                init, using_for_directive.library_name, self
            )
        elif isinstance(using_for_directive.library_name, SolcIdentifierPath):
            self._library_name = IdentifierPath(
                init, using_for_directive.library_name, self
            )

        if using_for_directive.type_name is None:
            self._type_name = None
        else:
            self._type_name = TypeNameAbc.from_ast(
                init, using_for_directive.type_name, self
            )

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        for function in self._functions:
            yield from function
        for function, _ in self._operator_functions:
            yield from function
        if self._library_name is not None:
            yield from self._library_name
        if self._type_name is not None:
            yield from self._type_name

    @property
    def parent(self) -> Union[ContractDefinition, SourceUnit]:
        """
        Returns:
            Parent IR node.
        """
        return self._parent

    @property
    def functions(self) -> Tuple[IdentifierPath, ...]:
        """
        Returns:
            List of functions that are attached to the target type.
        """
        return tuple(self._functions)

    @property
    def operator_functions(
        self,
    ) -> Tuple[Tuple[IdentifierPath, Union[UnaryOpOperator, BinaryOpOperator]], ...]:
        """
        Returns:
            List of operator functions and their operators that are attached to the target type.
        """
        return tuple(self._operator_functions)

    @property
    def library_name(self) -> Optional[Union[IdentifierPath, UserDefinedTypeName]]:
        """
        Is only set in the case of `:::solidity using LibraryName for TypeName;` directive type.

        Returns:
            IR node referencing the library ([ContractDefinition][wake.ir.declarations.contract_definition.ContractDefinition] of the [ContractKind.LIBRARY][wake.ir.enums.ContractKind.LIBRARY] kind) that is attached to the target type.
        """
        return self._library_name

    @property
    def type_name(self) -> Optional[TypeNameAbc]:
        """
        Is `None` in the case of `:::solidity using Lib for *;`.

        Returns:
            Type name that is attached to the functions or library.
        """
        return self._type_name
