from __future__ import annotations

import re
from bisect import bisect
from collections import deque
from functools import lru_cache, partial
from typing import (
    TYPE_CHECKING,
    Deque,
    FrozenSet,
    Iterator,
    List,
    Optional,
    Set,
    Tuple,
    Union,
)

from ...regex_parser import SoliditySourceParser
from ..meta.modifier_invocation import ModifierInvocation
from ..meta.override_specifier import OverrideSpecifier
from ..reference_resolver import CallbackParams
from ..statements.block import Block
from .abc import DeclarationAbc

if TYPE_CHECKING:
    from wake.analysis.cfg import ControlFlowGraph
    from .contract_definition import ContractDefinition
    from .variable_declaration import VariableDeclaration
    from ..expressions.identifier import Identifier
    from ..expressions.member_access import MemberAccess
    from ..meta.identifier_path import IdentifierPathPart
    from ..meta.source_unit import SourceUnit
    from ..statements.inline_assembly import ExternalReference
    from ..expressions.unary_operation import UnaryOperation
    from ..expressions.binary_operation import BinaryOperation

from wake.ir.abc import IrAbc, SolidityAbc
from wake.ir.ast import AstNodeId, SolcFunctionDefinition, SolcStructuredDocumentation
from wake.ir.enums import FunctionKind, StateMutability, Visibility
from wake.ir.meta.parameter_list import ParameterList
from wake.ir.meta.structured_documentation import StructuredDocumentation
from wake.ir.utils import IrInitTuple


class FunctionDefinition(DeclarationAbc):
    """
    Definition of a function.

    !!! example
        Free function (= outside of a contract):
        ```solidity linenums="1"
        function f(uint a, uint b) pure returns (uint) {
            return a + b;
        }
        ```

        Function inside a contract (lines 2-4):
        ```solidity linenums="1"
        contract C {
            function f(uint a, uint b) public pure returns (uint) {
                return a + b;
            }
        }
        ```

        Constructor (lines 3-5):
        ```solidity linenums="1"
        contract C {
            uint public x;
            constructor(uint a) public {
                x = a;
            }
        }
        ```

        Fallback function (line 2):
        ```solidity linenums="1"
        contract C {
            fallback() external payable {}
        }
        ```

        Receive function (line 2):
        ```solidity linenums="1"
        contract C {
            receive() external payable {}
        }
        ```
    """

    _ast_node: SolcFunctionDefinition
    _parent: Union[ContractDefinition, SourceUnit]
    _child_functions: Set[Union[FunctionDefinition, VariableDeclaration]]

    _implemented: bool
    _kind: FunctionKind
    _modifiers: List[ModifierInvocation]
    _parameters: ParameterList
    _return_parameters: ParameterList
    # __scope
    _state_mutability: StateMutability
    _virtual: bool
    _visibility: Visibility
    _base_functions: List[AstNodeId]
    _documentation: Optional[Union[StructuredDocumentation, str]]
    _function_selector: Optional[bytes]
    _body: Optional[Block]
    _overrides: Optional[OverrideSpecifier]

    def __init__(
        self, init: IrInitTuple, function: SolcFunctionDefinition, parent: SolidityAbc
    ):
        super().__init__(init, function, parent)
        self._child_functions = set()

        self._implemented = function.implemented
        self._kind = function.kind

        if self._kind == FunctionKind.CONSTRUCTOR:
            self._name = "constructor"
        elif self._kind == FunctionKind.FALLBACK:
            self._name = "fallback"
        elif self._kind == FunctionKind.RECEIVE:
            self._name = "receive"

        self._modifiers = [
            ModifierInvocation(init, modifier, self) for modifier in function.modifiers
        ]
        self._parameters = ParameterList(init, function.parameters, self)
        self._return_parameters = ParameterList(init, function.return_parameters, self)
        # self.__scope = function.scope
        self._state_mutability = function.state_mutability
        self._virtual = function.virtual
        self._visibility = function.visibility
        self._base_functions = (
            list(function.base_functions) if function.base_functions is not None else []
        )
        if function.documentation is None:
            self._documentation = None
        elif isinstance(function.documentation, SolcStructuredDocumentation):
            self._documentation = StructuredDocumentation(
                init, function.documentation, self
            )
        elif isinstance(function.documentation, str):
            self._documentation = function.documentation
        else:
            raise TypeError(
                f"Unknown type of documentation: {type(function.documentation)}"
            )
        self._function_selector = (
            bytes.fromhex(function.function_selector)
            if function.function_selector
            else None
        )

        if (
            self._visibility in {Visibility.PUBLIC, Visibility.EXTERNAL}
            and self._kind == FunctionKind.FUNCTION
        ):
            assert self._function_selector is not None
        else:
            assert self._function_selector is None

        self._body = Block(init, function.body, self) if function.body else None
        assert (self._body is not None) == self._implemented
        self._overrides = (
            OverrideSpecifier(init, function.overrides, self)
            if function.overrides
            else None
        )
        self._reference_resolver.register_post_process_callback(self._post_process)

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        for modifier in self._modifiers:
            yield from modifier
        yield from self._parameters
        yield from self._return_parameters
        if isinstance(self._documentation, StructuredDocumentation):
            yield from self._documentation
        if self._body is not None:
            yield from self._body
        if self._overrides is not None:
            yield from self._overrides

    def _post_process(self, callback_params: CallbackParams):
        base_functions = self.base_functions
        for base_function in base_functions:
            base_function._child_functions.add(self)
        self._reference_resolver.register_destroy_callback(
            self.source_unit.file, partial(self._destroy, base_functions)
        )

    def _destroy(self, base_functions: Tuple[FunctionDefinition, ...]) -> None:
        for base_function in base_functions:
            base_function._child_functions.remove(self)

    def _parse_name_location(self) -> Tuple[int, int]:
        IDENTIFIER = r"[a-zA-Z$_][a-zA-Z0-9$_]*"
        FUNCTION_RE = re.compile(
            r"^\s*function\s+(?P<name>{identifier})".format(
                identifier=IDENTIFIER
            ).encode("utf-8")
        )
        CONSTRUCTOR_RE = re.compile(r"^\s*(?P<name>constructor)".encode("utf-8"))
        FALLBACK_RE = re.compile(r"^\s*(?P<name>fallback)".encode("utf-8"))
        RECEIVE_RE = re.compile(r"^\s*(?P<name>receive)".encode("utf-8"))

        source = bytearray(self._source)
        _, stripped_sums = SoliditySourceParser.strip_comments(source)

        regexps = [FUNCTION_RE, CONSTRUCTOR_RE, FALLBACK_RE, RECEIVE_RE]
        matches = [regexp.match(source) for regexp in regexps]
        assert any(matches)

        byte_start = self._ast_node.src.byte_offset
        match = next(match for match in matches if match)

        if len(stripped_sums) == 0:
            stripped = 0
        else:
            index = bisect([s[0] for s in stripped_sums], match.start("name"))
            if index == 0:
                stripped = 0
            else:
                stripped = stripped_sums[index - 1][1]

        return (
            byte_start + match.start("name") + stripped,
            byte_start + match.end("name") + stripped,
        )

    def get_all_references(
        self, include_declarations: bool
    ) -> Iterator[
        Union[
            DeclarationAbc,
            Identifier,
            IdentifierPathPart,
            MemberAccess,
            ExternalReference,
            UnaryOperation,
            BinaryOperation,
        ]
    ]:
        from .variable_declaration import VariableDeclaration

        processed_declarations: Set[Union[FunctionDefinition, VariableDeclaration]] = {
            self
        }
        declarations_queue: Deque[
            Union[FunctionDefinition, VariableDeclaration]
        ] = deque([self])

        while declarations_queue:
            declaration = declarations_queue.pop()
            if include_declarations:
                yield declaration
            yield from declaration.references

            if isinstance(declaration, (FunctionDefinition, VariableDeclaration)):
                for base_function in declaration.base_functions:
                    if base_function not in processed_declarations:
                        declarations_queue.append(base_function)
                        processed_declarations.add(base_function)
            if isinstance(declaration, FunctionDefinition):
                for child_function in declaration.child_functions:
                    if child_function not in processed_declarations:
                        declarations_queue.append(child_function)
                        processed_declarations.add(child_function)

    @property
    def parent(self) -> Union[ContractDefinition, SourceUnit]:
        """
        Returns:
            Parent IR node.
        """
        return self._parent

    @property
    @lru_cache(maxsize=2048)
    def canonical_name(self) -> str:
        from .contract_definition import ContractDefinition

        if isinstance(self._parent, ContractDefinition):
            return f"{self._parent.canonical_name}.{self._name}({','.join(param.type_name.type_string for param in self._parameters.parameters)})"
        return f"{self._name}({','.join(param.type_name.type_string for param in self._parameters.parameters)})"

    @property
    @lru_cache(maxsize=2048)
    def declaration_string(self) -> str:
        if self.kind == FunctionKind.CONSTRUCTOR:
            ret = "constructor"
        elif self.kind == FunctionKind.FALLBACK:
            ret = "fallback"
        elif self.kind == FunctionKind.RECEIVE:
            ret = "receive"
        else:
            ret = f"function {self.name}"
        ret += f"({', '.join(parameter.declaration_string for parameter in self.parameters.parameters)})"
        ret += f" {self.visibility}"
        ret += (
            f" {self.state_mutability}"
            if self.state_mutability != StateMutability.NONPAYABLE
            else ""
        )
        ret += f" virtual" if self.virtual else ""
        ret += (
            (
                f" override"
                + (
                    "("
                    + ", ".join(
                        override.source for override in self.overrides.overrides
                    )
                    + ")"
                    if len(self.overrides.overrides) > 0
                    else ""
                )
            )
            if self.overrides is not None
            else ""
        )
        ret += (
            (" " + " ".join(modifier.source for modifier in self.modifiers))
            if len(self.modifiers) > 0
            else ""
        )
        ret += (
            " returns ("
            + ", ".join(
                parameter.declaration_string
                for parameter in self.return_parameters.parameters
            )
            + ")"
            if len(self.return_parameters.parameters) > 0
            else ""
        )

        if isinstance(self.documentation, StructuredDocumentation):
            return (
                "/// "
                + "\n///".join(line for line in self.documentation.text.splitlines())
                + "\n"
                + ret
            )
        elif isinstance(self.documentation, str):
            return (
                "/// "
                + "\n///".join(line for line in self.documentation.splitlines())
                + "\n"
                + ret
            )
        else:
            return ret

    @property
    def implemented(self) -> bool:
        """
        Returns:
            `True` if the function [body][wake.ir.declarations.function_definition.FunctionDefinition.body] is not `None`, `False` otherwise.
        """
        return self._implemented

    @property
    def kind(self) -> FunctionKind:
        """
        Returns:
            Kind of the function.
        """
        return self._kind

    @property
    def modifiers(self) -> Tuple[ModifierInvocation, ...]:
        """
        Also includes base constructor invocations.
        !!! example
            Both `:::solidity ERC20Token("My Token", "MTK", msg.sender, 10 ** 18)` and `initializer` are listed by this property.
            ```solidity
            contract MyToken is ERC20Token {
                constructor() ERC20Token("My Token", "MTK", msg.sender, 10 ** 18) initializer {}
            }
            ```

        Returns:
            List of modifiers applied to the function.
        """
        return tuple(self._modifiers)

    @property
    def parameters(self) -> ParameterList:
        """
        Returns:
            Parameter list describing the function parameters.
        """
        return self._parameters

    @property
    def return_parameters(self) -> ParameterList:
        """
        Returns:
            Parameter list describing the function return parameters.
        """
        return self._return_parameters

    @property
    def state_mutability(self) -> StateMutability:
        """
        Returns:
            State mutability of the function.
        """
        return self._state_mutability

    @property
    def virtual(self) -> bool:
        """
        Returns:
            `True` if the function is virtual, `False` otherwise.
        """
        return self._virtual

    @property
    def visibility(self) -> Visibility:
        """
        Returns:
            Visibility of the function.
        """
        return self._visibility

    @property
    def base_functions(self) -> Tuple[FunctionDefinition, ...]:
        """
        !!! example
            `A.foo` on lines 6-8 lists `I.foo` on line 2 as a base function.

            `B.foo` on lines 12-14 lists only `A.foo` on lines 6-8 as a base function.
            ```solidity linenums="1"
            interface I {
                function foo() external returns(uint);
            }

            contract A is I {
                function foo() external pure virtual override returns(uint) {
                    return 1;
                }
            }

            contract B is A {
                function foo() external pure override returns(uint) {
                    return 2;
                }
            }
            ```

        !!! example
            `A1.foo` on lines 6-8 lists `I.foo` on line 2 as a base function.

            `A2.foo` on lines 12-14 lists `I.foo` on line 2 as a base function.

            `B.foo` on lines 18-20 lists `A1.foo` on lines 6-8 and `A2.foo` on lines 12-14 as base functions.
            ```solidity linenums="1"
            interface I {
                function foo() external returns(uint);
            }

            contract A1 is I {
                function foo() external pure virtual override returns(uint) {
                    return 1;
                }
            }

            contract A2 is I {
                function foo() external pure virtual override returns(uint) {
                    return 2;
                }
            }

            contract B is A1, A2 {
                function foo() external pure override(A1, A2) returns(uint) {
                    return 3;
                }
            }
            ```

        Returns:
            List of base functions overridden by this function.
        """
        base_functions = []
        for base_function_id in self._base_functions:
            base_function = self._reference_resolver.resolve_node(
                base_function_id, self.source_unit.cu_hash
            )
            assert isinstance(base_function, FunctionDefinition)
            base_functions.append(base_function)
        return tuple(base_functions)

    @property
    def child_functions(
        self,
    ) -> FrozenSet[Union[FunctionDefinition, VariableDeclaration]]:
        """
        Returns:
            Functions that list this function in their [base_functions][wake.ir.declarations.function_definition.FunctionDefinition.base_functions] property.
        """
        return frozenset(self._child_functions)

    @property
    def documentation(self) -> Optional[Union[StructuredDocumentation, str]]:
        """
        Of [StructuredDocumentation][wake.ir.meta.structured_documentation.StructuredDocumentation] type since Solidity 0.6.3.

        Returns:
            [NatSpec](https://solidity.readthedocs.io/en/latest/natspec-format.html) documentation string, if any.
        """
        return self._documentation

    @property
    def function_selector(self) -> Optional[bytes]:
        """
        Is only set for [Visibility.PUBLIC][wake.ir.enums.Visibility.PUBLIC] and [Visibility.EXTERNAL][wake.ir.enums.Visibility.EXTERNAL] functions of the [FunctionKind.FUNCTION][wake.ir.enums.FunctionKind.FUNCTION] kind.

        Returns:
            Selector of the function.
        """
        return self._function_selector

    @property
    def body(self) -> Optional[Block]:
        """
        Returns:
            Body of the function, if any.
        """
        return self._body

    @property
    def overrides(self) -> Optional[OverrideSpecifier]:
        """
        Returns override specifier as present in the source code.
        !!! example
            `I.foo` on line 2 does not have an override specifier.

            `A.foo` on lines 6-8 has an override specifier with the [overrides][wake.ir.meta.override_specifier.OverrideSpecifier.overrides] property empty.

            `B.foo` on lines 12-14 has an override specifier with the [overrides][wake.ir.meta.override_specifier.OverrideSpecifier.overrides] property containg one item referencing the contract `A` ([ContractDefinition][wake.ir.declarations.contract_definition.ContractDefinition]).
            ```solidity linenums="1"
            interface I {
                function foo() external returns(uint);
            }

            contract A is I {
                function foo() external pure virtual override returns(uint) {
                    return 1;
                }
            }

            contract B is A {
                function foo() external pure override(A) returns(uint) {
                    return 2;
                }
            }
            ```

        Returns:
            Override specifier, if any.
        """
        return self._overrides

    @property
    @lru_cache(maxsize=128)
    def cfg(self) -> ControlFlowGraph:
        """
        Raises:
            ValueError: If the function is not implemented.

        Returns:
            Control flow graph of the function.
        """
        from wake.analysis.cfg import ControlFlowGraph

        if not self._implemented:
            raise ValueError("Cannot create CFG for unimplemented function")

        return ControlFlowGraph(self)

    @property
    def references(
        self,
    ) -> FrozenSet[
        Union[
            Identifier,
            IdentifierPathPart,
            MemberAccess,
            UnaryOperation,
            BinaryOperation,
        ]
    ]:
        """
        Returns:
            Set of all IR nodes referencing this function.
        """
        from ..expressions.binary_operation import BinaryOperation
        from ..expressions.identifier import Identifier
        from ..expressions.member_access import MemberAccess
        from ..expressions.unary_operation import UnaryOperation
        from ..meta.identifier_path import IdentifierPathPart

        try:
            ref = next(
                ref
                for ref in self._references
                if not isinstance(
                    ref,
                    (
                        Identifier,
                        IdentifierPathPart,
                        MemberAccess,
                        UnaryOperation,
                        BinaryOperation,
                    ),
                )
            )
            raise AssertionError(f"Unexpected reference type: {ref}")
        except StopIteration:
            return frozenset(
                self._references
            )  # pyright: ignore reportGeneralTypeIssues
