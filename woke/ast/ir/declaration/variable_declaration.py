from __future__ import annotations

import logging
import re
from functools import lru_cache, partial
from typing import TYPE_CHECKING, Iterator, List, Optional, Tuple, Union

from woke.ast.enums import DataLocation, Mutability, Visibility
from woke.ast.ir.abc import IrAbc, SolidityAbc
from woke.ast.ir.declaration.abc import DeclarationAbc
from woke.ast.ir.expression.abc import ExpressionAbc
from woke.ast.ir.meta.structured_documentation import StructuredDocumentation
from woke.ast.ir.type_name.abc import TypeNameAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import AstNodeId, SolcVariableDeclaration, TypeDescriptionsModel
from woke.utils.string import StringReader

from ...types import TypeAbc
from ..meta.override_specifier import OverrideSpecifier
from ..reference_resolver import CallbackParams

if TYPE_CHECKING:
    from ..declaration.contract_definition import ContractDefinition
    from ..declaration.function_definition import FunctionDefinition
    from ..declaration.struct_definition import StructDefinition
    from ..meta.parameter_list import ParameterList
    from ..meta.source_unit import SourceUnit
    from ..statement.variable_declaration_statement import VariableDeclarationStatement


logger = logging.getLogger(__name__)


class VariableDeclaration(DeclarationAbc):
    """
    !!! example
        A variable can be declared:

        - inside a [ContractDefinition][woke.ast.ir.declaration.contract_definition.ContractDefinition] as a state variable:
            - `:::solidity uint public stateVar` in line 4,
        - inside a [ParameterList][woke.ast.ir.meta.parameter_list.ParameterList]:
            - in an [ErrorDefinition][woke.ast.ir.declaration.error_definition.ErrorDefinition] parameters:
                - `:::solidity uint errorArg` in line 5,
            - in an [EventDefinition][woke.ast.ir.declaration.event_definition.EventDefinition] parameters:
                - `:::solidity uint indexed eventArg` in line 6,
            - in a [FunctionDefinition][woke.ast.ir.declaration.function_definition.FunctionDefinition] parameters or return parameters:
                - `:::solidity uint funcReturnArg` in line 16
                - `:::solidity uint x` and `:::solidity uint` in line 20
                - `:::solidity uint` in line 30
                - `:::solidity function (uint) pure returns(uint) h` and the third occurrence `:::solidity uint` in line 34,
            - in a [ModifierDefinition][woke.ast.ir.declaration.modifier_definition.ModifierDefinition] parameters:
                - `:::solidity uint modifierArg` in line 12,
            - in a [FunctionTypeName][woke.ast.ir.type_name.function_type_name.FunctionTypeName] parameters or return parameters:
                - the first two occurrences of `:::solidity uint` in line 34,
            - in a [TryCatchClause][woke.ast.ir.meta.try_catch_clause.TryCatchClause]:
                - `:::solidity uint z` in line 22
                - `:::solidity string memory reason` in line 24,
        - inside a [SourceUnit][woke.ast.ir.meta.source_unit.SourceUnit] only as a constant variable:
            - `:::solidity uint constant CONST = 10` in line 1,
        - inside a [StructDefinition][woke.ast.ir.declaration.struct_definition.StructDefinition] as a member variable:
            - `:::solidity uint structMember` in line 9,
        - inside a [VariableDeclarationStatement][woke.ast.ir.statement.variable_declaration_statement.VariableDeclarationStatement] in a [FunctionDefinition.body][woke.ast.ir.declaration.function_definition.FunctionDefinition.body] as a local variable:
            - `:::solidity uint y = x` in line 21.

        ```solidity linenums="1"
        uint constant CONST = 10;

        contract C {
            uint public stateVar;
            error E(uint errorArg);
            event F(uint indexed eventArg);

            struct S {
                uint structMember;
            }

            modifier M(uint modifierArg) {
                _;
            }

            function foo() public pure returns (uint funcReturnArg) {
                funcReturnArg = 7;
            }

            function f(uint x) public view returns (uint) {
                uint y = x;
                try this.tmp() returns (uint z) {
                    y = z;
                } catch Error(string memory reason) {
                    revert(reason);
                }
                return y;
            }

            function tmp() external pure returns(uint) {
                return CONST;
            }

            function g(function (uint) pure returns(uint) h) internal pure returns (uint) {
                return h(7);
            }
        }
        ```
    """

    _ast_node: SolcVariableDeclaration
    _parent: Union[
        ContractDefinition,
        ParameterList,
        SourceUnit,
        StructDefinition,
        VariableDeclarationStatement,
    ]

    _constant: bool
    # __scope
    _mutability: Optional[Mutability]
    _state_variable: bool
    _data_location: DataLocation
    _visibility: Visibility
    _base_functions: List[AstNodeId]
    _documentation: Optional[StructuredDocumentation]
    _function_selector: Optional[bytes]
    _indexed: bool
    _overrides: Optional[OverrideSpecifier]
    _type_name: TypeNameAbc
    _value: Optional[ExpressionAbc]
    _type_descriptions: TypeDescriptionsModel

    def __init__(
        self,
        init: IrInitTuple,
        variable_declaration: SolcVariableDeclaration,
        parent: SolidityAbc,
    ):
        super().__init__(init, variable_declaration, parent)
        self._constant = variable_declaration.constant
        self._mutability = variable_declaration.mutability
        # TODO scope
        self._state_variable = variable_declaration.state_variable
        self._data_location = variable_declaration.storage_location
        self._visibility = variable_declaration.visibility
        self._base_functions = (
            list(variable_declaration.base_functions)
            if variable_declaration.base_functions is not None
            else []
        )
        self._documentation = (
            StructuredDocumentation(init, variable_declaration.documentation, self)
            if variable_declaration.documentation
            else None
        )
        self._function_selector = (
            bytes.fromhex(variable_declaration.function_selector)
            if variable_declaration.function_selector
            else None
        )
        self._indexed = variable_declaration.indexed or False
        self._overrides = (
            OverrideSpecifier(init, variable_declaration.overrides, self)
            if variable_declaration.overrides
            else None
        )

        # type name should not be None
        # prior 0.5.0, there was a `var` keyword which resulted in the type name being None
        assert (
            variable_declaration.type_name is not None
        ), "Variable declaration must have a type name"
        self._type_name = TypeNameAbc.from_ast(
            init, variable_declaration.type_name, self
        )
        self._value = (
            ExpressionAbc.from_ast(init, variable_declaration.value, self)
            if variable_declaration.value is not None
            else None
        )
        self._type_descriptions = variable_declaration.type_descriptions
        self._reference_resolver.register_post_process_callback(self._post_process)

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        if self._documentation is not None:
            yield from self._documentation
        if self._overrides is not None:
            yield from self._overrides
        yield from self._type_name
        if self._value is not None:
            yield from self._value

    def _post_process(self, callback_params: CallbackParams):
        base_functions = self.base_functions
        for base_function in base_functions:
            base_function._child_functions.add(self)
        self._reference_resolver.register_destroy_callback(
            self.file, partial(self._destroy, base_functions)
        )

    def _destroy(self, base_functions: Tuple[FunctionDefinition]) -> None:
        for base_function in base_functions:
            base_function._child_functions.discard(self)

    def _parse_name_location(self) -> Tuple[int, int]:
        # this one is a bit tricky
        # it is easier to parse the variable declaration from the end (while omitting an optional assigned expression)
        if self._value is None:
            source_without_value = self._source
        else:
            length_without_value = self._value.byte_location[0] - self.byte_location[0]
            source_without_value = self._source[:length_without_value]

        IDENTIFIER = r"[a-zA-Z$_][a-zA-Z0-9$_]*"
        VARIABLE_RE = re.compile(
            r"(?P<name>{identifier})(\s*=)?\s*$".format(identifier=IDENTIFIER).encode(
                "utf-8"
            )
        )
        match = VARIABLE_RE.search(source_without_value)
        assert match
        byte_start = self._ast_node.src.byte_offset
        return byte_start + match.start("name"), byte_start + match.end("name")

    @property
    def parent(
        self,
    ) -> Union[
        ContractDefinition,
        ParameterList,
        SourceUnit,
        StructDefinition,
        VariableDeclarationStatement,
    ]:
        """
        Returns:
            Parent IR node.
        """
        return self._parent

    @property
    @lru_cache(maxsize=2048)
    def canonical_name(self) -> str:
        node = self.parent
        while node is not None:
            if isinstance(node, DeclarationAbc):
                break
            node = node.parent
        if node is None:
            return self.name
        return f"{node.canonical_name}.{self.name}"

    @property
    @lru_cache(maxsize=2048)
    def declaration_string(self) -> str:
        ret = self.type_name.source
        ret += f" {self.visibility}" if self.is_state_variable else ""
        ret += f" {self.mutability}" if self.mutability != Mutability.MUTABLE else ""
        ret += (
            f" {self.data_location}"
            if self.data_location != DataLocation.DEFAULT
            else ""
        )
        ret += (
            (
                f" override"
                + ", ".join(override.source for override in self.overrides.overrides)
            )
            if self.overrides is not None
            else ""
        )
        ret += f" {self.name}" if len(self.name) > 0 else ""
        ret += (
            f" = {self.value.source}"
            if self.value is not None and self.mutability == Mutability.CONSTANT
            else ""
        )

        if self.documentation is not None:
            return (
                "/// "
                + "\n///".join(line for line in self.documentation.text.splitlines())
                + "\n"
                + ret
            )
        return ret

    @property
    def mutability(self) -> Mutability:
        """
        Returns:
            Mutability of the variable.
        """
        if self._mutability is None:
            relative_type_end = self._type_name.byte_location[1] - self.byte_location[0]
            relative_name_start = self.name_location[0] - self.byte_location[0]
            keywords_source = self._source[relative_type_end:relative_name_start]

            if b"immutable" in keywords_source:
                self._mutability = Mutability.IMMUTABLE
            elif self._constant:
                self._mutability = Mutability.CONSTANT
            else:
                self._mutability = Mutability.MUTABLE
        return self._mutability

    @property
    def is_state_variable(self) -> bool:
        """
        Returns:
            `True` if the variable is a state variable, `False` otherwise.
        """
        return self._state_variable

    @property
    def data_location(self) -> DataLocation:
        """
        [DataLocation.DEFAULT][woke.ast.enums.DataLocation.DEFAULT] is returned if the data location is not specified in the source code.
        Returns:
            Data location of the variable.
        """
        return self._data_location

    @property
    def visibility(self) -> Visibility:
        """
        Returns:
            Visibility of the variable.
        """
        return self._visibility

    @property
    def base_functions(self) -> Tuple[FunctionDefinition]:
        """
        !!! example
            `C.foo` in line 6 lists `I.foo` in line 2 as a base function.
            ```solidity linenums="1"
            interface I {
                function foo(uint, bool) external returns(uint);
            }

            contract C is I {
                mapping(uint => mapping(bool => uint)) public override foo;
            }
            ```

        !!! example
            `B.foo` in line 14 lists `A1.foo` in lines 2-4 and `A2.foo` in lines 8-10 as base functions.
            ```solidity linenums="1"
            contract A1 {
                function foo(uint, bool) external virtual returns(uint) {
                    return 1;
                }
            }

            contract A2 {
                function foo(uint, bool) external virtual returns(uint) {
                    return 2;
                }
            }

            contract B is A1, A2 {
                mapping(uint => mapping(bool => uint)) public override(A1, A2) foo;
            }
            ```

        Returns:
            List of base functions overridden by this function.
        """
        from ..declaration.function_definition import FunctionDefinition

        base_functions = []
        for base_function_id in self._base_functions:
            base_function = self._reference_resolver.resolve_node(
                base_function_id, self._cu_hash
            )
            assert isinstance(base_function, FunctionDefinition)
            base_functions.append(base_function)
        return tuple(base_functions)

    @property
    def documentation(self) -> Optional[StructuredDocumentation]:
        """
        Returns:
            [NatSpec](https://docs.soliditylang.org/en/latest/natspec-format.html) documentation string, if any.
        """
        return self._documentation

    @property
    def function_selector(self) -> Optional[bytes]:
        """
        Is only set for public state variables.
        Returns:
            Function selector of the getter function generated for this variable, if any.
        """
        return self._function_selector

    @property
    def indexed(self) -> bool:
        """
        Returns:
            `True` if the variable is indexed, `False` otherwise.
        """
        return self._indexed

    @property
    def overrides(self) -> Optional[OverrideSpecifier]:
        """
        Returns override specified as specified in the source code.

        !!! example
            `A1.foo` in lines 2-4 and `A2.foo` in lines 8-10 do not have an override specifier.

            `B.foo` in line 14 has an override specifier with the [overrides][woke.ast.ir.meta.override_specifier.OverrideSpecifier.overrides] property containing two items referencing the contracts `A1` and `A2` ([ContractDefinition][woke.ast.ir.declaration.contract_definition.ContractDefinition]).
            ```solidity linenums="1"
            contract A1 {
                function foo(uint, bool) external virtual returns(uint) {
                    return 1;
                }
            }

            contract A2 {
                function foo(uint, bool) external virtual returns(uint) {
                    return 2;
                }
            }

            contract B is A1, A2 {
                mapping(uint => mapping(bool => uint)) public override(A1, A2) foo;
            }
            ```

        Returns:
            Override specifier, if any.
        """
        return self._overrides

    @property
    def type_name(self) -> TypeNameAbc:
        """
        Returns:
            Type name IR node as present in the source code.
        """
        return self._type_name

    @property
    def value(self) -> Optional[ExpressionAbc]:
        """
        Is not set if the parent is a [VariableDeclarationStatement][woke.ast.ir.statement.variable_declaration_statement.VariableDeclarationStatement].
        In this case, the initial value (if any) is set in the [VariableDeclarationStatement.initial_value][woke.ast.ir.statement.variable_declaration_statement.VariableDeclarationStatement.initial_value] property.
        Returns:
            Initial value expression assigned to the variable in this declaration, if any.
        """
        return self._value

    @property
    @lru_cache(maxsize=2048)
    def type(self) -> TypeAbc:
        """
        Returns:
            Type of the variable.
        """
        assert self._type_descriptions.type_identifier is not None

        type_identifier = StringReader(self._type_descriptions.type_identifier)
        ret = TypeAbc.from_type_identifier(
            type_identifier, self._reference_resolver, self.cu_hash
        )
        assert (
            len(type_identifier) == 0 and ret is not None
        ), f"Failed to parse type identifier: {self._type_descriptions.type_identifier}"
        return ret

    @property
    def type_string(self) -> str:
        """
        Returns:
            User-friendly string describing the variable type.
        """
        assert self._type_descriptions.type_string is not None
        return self._type_descriptions.type_string
