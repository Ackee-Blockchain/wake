from __future__ import annotations

import re
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

from ..meta.modifier_invocation import ModifierInvocation
from ..meta.override_specifier import OverrideSpecifier
from ..reference_resolver import CallbackParams
from ..statement.block import Block
from .abc import DeclarationAbc

if TYPE_CHECKING:
    from woke.analysis.cfg import ControlFlowGraph
    from .contract_definition import ContractDefinition
    from .variable_declaration import VariableDeclaration
    from ..expression.identifier import Identifier
    from ..expression.member_access import MemberAccess
    from ..meta.identifier_path import IdentifierPathPart
    from ..meta.source_unit import SourceUnit
    from ..statement.inline_assembly import ExternalReference

from woke.ast.enums import FunctionKind, StateMutability, Visibility
from woke.ast.ir.abc import IrAbc, SolidityAbc
from woke.ast.ir.meta.parameter_list import ParameterList
from woke.ast.ir.meta.structured_documentation import StructuredDocumentation
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import (
    AstNodeId,
    SolcFunctionDefinition,
    SolcStructuredDocumentation,
)


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

    __implemented: bool
    __kind: FunctionKind
    __modifiers: List[ModifierInvocation]
    __parameters: ParameterList
    __return_parameters: ParameterList
    # __scope
    __state_mutability: StateMutability
    __virtual: bool
    __visibility: Visibility
    __base_functions: List[AstNodeId]
    __documentation: Optional[Union[StructuredDocumentation, str]]
    __function_selector: Optional[bytes]
    __body: Optional[Block]
    __overrides: Optional[OverrideSpecifier]

    def __init__(
        self, init: IrInitTuple, function: SolcFunctionDefinition, parent: SolidityAbc
    ):
        super().__init__(init, function, parent)
        self._child_functions = set()

        self.__implemented = function.implemented
        self.__kind = function.kind

        if self.__kind == FunctionKind.CONSTRUCTOR:
            self._name = "constructor"
        elif self.__kind == FunctionKind.FALLBACK:
            self._name = "fallback"
        elif self.__kind == FunctionKind.RECEIVE:
            self._name = "receive"

        self.__modifiers = [
            ModifierInvocation(init, modifier, self) for modifier in function.modifiers
        ]
        self.__parameters = ParameterList(init, function.parameters, self)
        self.__return_parameters = ParameterList(init, function.return_parameters, self)
        # self.__scope = function.scope
        self.__state_mutability = function.state_mutability
        self.__virtual = function.virtual
        self.__visibility = function.visibility
        self.__base_functions = (
            list(function.base_functions) if function.base_functions is not None else []
        )
        if function.documentation is None:
            self.__documentation = None
        elif isinstance(function.documentation, SolcStructuredDocumentation):
            self.__documentation = StructuredDocumentation(
                init, function.documentation, self
            )
        elif isinstance(function.documentation, str):
            self.__documentation = function.documentation
        else:
            raise TypeError(
                f"Unknown type of documentation: {type(function.documentation)}"
            )
        self.__function_selector = (
            bytes.fromhex(function.function_selector)
            if function.function_selector
            else None
        )

        if (
            self.__visibility in {Visibility.PUBLIC, Visibility.EXTERNAL}
            and self.__kind == FunctionKind.FUNCTION
        ):
            assert self.__function_selector is not None
        else:
            assert self.__function_selector is None

        self.__body = Block(init, function.body, self) if function.body else None
        assert (self.__body is not None) == self.__implemented
        self.__overrides = (
            OverrideSpecifier(init, function.overrides, self)
            if function.overrides
            else None
        )
        self._reference_resolver.register_post_process_callback(self.__post_process)

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        for modifier in self.__modifiers:
            yield from modifier
        yield from self.__parameters
        yield from self.__return_parameters
        if isinstance(self.__documentation, StructuredDocumentation):
            yield from self.__documentation
        if self.__body is not None:
            yield from self.__body
        if self.__overrides is not None:
            yield from self.__overrides

    def __post_process(self, callback_params: CallbackParams):
        base_functions = self.base_functions
        for base_function in base_functions:
            base_function._child_functions.add(self)
        self._reference_resolver.register_destroy_callback(
            self.file, partial(self.__destroy, base_functions)
        )

    def __destroy(self, base_functions: Tuple[FunctionDefinition]) -> None:
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

        regexps = [FUNCTION_RE, CONSTRUCTOR_RE, FALLBACK_RE, RECEIVE_RE]
        matches = [regexp.match(self._source) for regexp in regexps]
        assert any(matches)

        byte_start = self._ast_node.src.byte_offset
        match = next(match for match in matches if match)
        return byte_start + match.start("name"), byte_start + match.end("name")

    def get_all_references(
        self, include_declarations: bool
    ) -> Iterator[Union[DeclarationAbc, Identifier, IdentifierPathPart, MemberAccess, ExternalReference]]:
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
    @lru_cache(maxsize=None)
    def canonical_name(self) -> str:
        from .contract_definition import ContractDefinition

        if isinstance(self._parent, ContractDefinition):
            return f"{self._parent.canonical_name}.{self._name}"
        return self.name

    @property
    @lru_cache(maxsize=None)
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
            `True` if the function [body][woke.ast.ir.declaration.function_definition.FunctionDefinition.body] is not `None`, `False` otherwise.
        """
        return self.__implemented

    @property
    def kind(self) -> FunctionKind:
        """
        Returns:
            Kind of the function.
        """
        return self.__kind

    @property
    def modifiers(self) -> Tuple[ModifierInvocation]:
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
        return tuple(self.__modifiers)

    @property
    def parameters(self) -> ParameterList:
        """
        Returns:
            Parameter list describing the function parameters.
        """
        return self.__parameters

    @property
    def return_parameters(self) -> ParameterList:
        """
        Returns:
            Parameter list describing the function return parameters.
        """
        return self.__return_parameters

    @property
    def state_mutability(self) -> StateMutability:
        """
        Returns:
            State mutability of the function.
        """
        return self.__state_mutability

    @property
    def virtual(self) -> bool:
        """
        Returns:
            `True` if the function is virtual, `False` otherwise.
        """
        return self.__virtual

    @property
    def visibility(self) -> Visibility:
        """
        Returns:
            Visibility of the function.
        """
        return self.__visibility

    @property
    def base_functions(self) -> Tuple[FunctionDefinition]:
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
        for base_function_id in self.__base_functions:
            base_function = self._reference_resolver.resolve_node(
                base_function_id, self._cu_hash
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
            Functions that list this function in their [base_functions][woke.ast.ir.declaration.function_definition.FunctionDefinition.base_functions] property.
        """
        return frozenset(self._child_functions)

    @property
    def documentation(self) -> Optional[Union[StructuredDocumentation, str]]:
        """
        Of [StructuredDocumentation][woke.ast.ir.meta.structured_documentation.StructuredDocumentation] type since Solidity 0.6.3.
        Returns:
            [NatSpec](https://solidity.readthedocs.io/en/latest/natspec-format.html) documentation string, if any.
        """
        return self.__documentation

    @property
    def function_selector(self) -> Optional[bytes]:
        """
        Is only set for [Visibility.PUBLIC][woke.ast.enums.Visibility.PUBLIC] and [Visibility.EXTERNAL][woke.ast.enums.Visibility.EXTERNAL] functions of the [FunctionKind.FUNCTION][woke.ast.enums.FunctionKind.FUNCTION] kind.
        Returns:
            Selector of the function.
        """
        return self.__function_selector

    @property
    def body(self) -> Optional[Block]:
        """
        Returns:
            Body of the function, if any.
        """
        return self.__body

    @property
    def overrides(self) -> Optional[OverrideSpecifier]:
        """
        Returns override specifier as present in the source code.
        !!! example
            `I.foo` on line 2 does not have an override specifier.

            `A.foo` on lines 6-8 has an override specifier with the [overrides][woke.ast.ir.meta.override_specifier.OverrideSpecifier.overrides] property empty.

            `B.foo` on lines 12-14 has an override specifier with the [overrides][woke.ast.ir.meta.override_specifier.OverrideSpecifier.overrides] property containg one item referencing the contract `A` ([ContractDefinition][woke.ast.ir.declaration.contract_definition.ContractDefinition]).
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
        return self.__overrides

    @property
    @lru_cache(maxsize=None)
    def cfg(self) -> Optional[ControlFlowGraph]:
        from woke.analysis.cfg import ControlFlowGraph
        if self.body is None:
            return None
        return ControlFlowGraph(self)
