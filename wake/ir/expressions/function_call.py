from __future__ import annotations

import weakref
from typing import Iterator, List, Optional, Tuple, Union

from wake.core import get_logger
from wake.ir.abc import IrAbc, SolidityAbc
from wake.ir.enums import FunctionCallKind, GlobalSymbol
from wake.utils.decorators import weak_self_lru_cache

from ..ast import SolcFunctionCall
from ..declarations.contract_definition import ContractDefinition
from ..declarations.error_definition import ErrorDefinition
from ..declarations.event_definition import EventDefinition
from ..declarations.function_definition import FunctionDefinition
from ..declarations.struct_definition import StructDefinition
from ..declarations.variable_declaration import VariableDeclaration
from ..expressions.abc import ExpressionAbc
from ..expressions.function_call_options import FunctionCallOptions
from ..expressions.identifier import Identifier
from ..expressions.member_access import MemberAccess
from ..expressions.new_expression import NewExpression
from ..expressions.tuple_expression import TupleExpression
from ..type_names.array_type_name import ArrayTypeName
from ..type_names.elementary_type_name import ElementaryTypeName
from ..type_names.user_defined_type_name import UserDefinedTypeName
from ..utils import IrInitTuple

logger = get_logger(__name__)


class FunctionCall(ExpressionAbc):
    """
    Represents:

    - function calls, e.g. `:::solidity address(this).call("")`,
    - type conversions, e.g. `:::solidity address(this)`,
    - struct constructor calls, e.g. `:::solidity MyStruct({a: 1, b: 2})`,
    - contract creation calls, e.g. `:::solidity new MyContract{value: 1}()`,
    - dynamic array creations calls (including `:::solidity bytes` and `:::solidity string`), e.g. `:::solidity new uint[](10)` or `:::solidity new bytes(10)`,
    - event emit calls, e.g. `:::solidity MyEvent(1, 2)` in `emit MyEvent(1, 2)`,
    - error revert calls, e.g. `:::solidity MyError(1, 2)` in `revert MyError(1, 2)`,
    - variable getter calls.
    """

    _ast_node: SolcFunctionCall
    _parent: weakref.ReferenceType[SolidityAbc]  # TODO: make this more specific

    _arguments: List[ExpressionAbc]
    _expression: ExpressionAbc
    _kind: FunctionCallKind
    _names: List[str]
    _try_call: bool

    def __init__(
        self, init: IrInitTuple, function_call: SolcFunctionCall, parent: SolidityAbc
    ):
        super().__init__(init, function_call, parent)
        self._kind = function_call.kind
        self._names = list(function_call.names)
        self._try_call = function_call.try_call

        self._expression = ExpressionAbc.from_ast(init, function_call.expression, self)
        self._arguments = [
            ExpressionAbc.from_ast(init, argument, self)
            for argument in function_call.arguments
        ]

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        for argument in self._arguments:
            yield from argument
        yield from self._expression

    @property
    def parent(self) -> SolidityAbc:
        return super().parent

    @property
    def children(self) -> Iterator[ExpressionAbc]:
        """
        Yields:
            Direct children of this node.
        """
        yield self._expression
        yield from self._arguments

    @property
    def kind(self) -> FunctionCallKind:
        """
        [FunctionCallKind.FUNCTION_CALL][wake.ir.enums.FunctionCallKind.FUNCTION_CALL] is except for
        function calls also used for:

        - contract construction using [NewExpression][wake.ir.expressions.new_expression.NewExpression]
        - new dynamic array creation using [NewExpression][wake.ir.expressions.new_expression.NewExpression]
        - variable getter calls

        Returns:
            Kind of function call.
        """
        return self._kind

    @property
    def names(self) -> Tuple[str, ...]:
        """
        Is empty if the function call does not use named arguments.

        !!! example
            `("to", "value")` for the following function call:
            ```solidity
            token.transfer({to: msg.sender, value: 100});
            ```

        Returns:
            Tuple of names of the named arguments in the order they appear in the source code.
        """
        return tuple(self._names)

    @property
    def try_call(self) -> bool:
        """
        !!! example
            Is `True` for `this.foo()` in the following code:
            ```solidity
            try this.foo() {} catch {}
            ```

        Returns:
            True if the function call is a try call, False otherwise.
        """
        return self._try_call

    @property
    def expression(self) -> ExpressionAbc:
        """
        Returns:
            Expression that evaluates to the function being called.
        """
        return self._expression

    @property
    def arguments(self) -> Tuple[ExpressionAbc, ...]:
        """
        Returns:
            Tuple of arguments of the function call in the order they appear in the source code.
        """
        return tuple(self._arguments)

    @property
    def function_called(
        self,
    ) -> Optional[
        Union[
            ContractDefinition,  # contract construction
            ArrayTypeName,  # new dynamic array
            ElementaryTypeName,  # new string or bytes
            EventDefinition,
            ErrorDefinition,
            FunctionDefinition,
            GlobalSymbol,
            StructDefinition,
            VariableDeclaration,
        ]
    ]:
        if self.kind == FunctionCallKind.TYPE_CONVERSION:
            return None

        node = self.expression
        while True:
            if isinstance(node, Identifier):
                referenced_declaration = node.referenced_declaration
                if isinstance(
                    referenced_declaration,
                    (
                        EventDefinition,
                        ErrorDefinition,
                        FunctionDefinition,
                        GlobalSymbol,
                        StructDefinition,
                        VariableDeclaration,
                    ),
                ):
                    return referenced_declaration
                else:
                    assert (
                        False
                    ), f"Unexpected function call referenced declaration type: {referenced_declaration}"
            elif isinstance(node, MemberAccess):
                referenced_declaration = node.referenced_declaration
                if isinstance(
                    referenced_declaration,
                    (
                        EventDefinition,
                        ErrorDefinition,
                        FunctionDefinition,
                        GlobalSymbol,
                        StructDefinition,
                        VariableDeclaration,
                    ),
                ):
                    return referenced_declaration
                else:
                    assert (
                        False
                    ), f"Unexpected function call referenced declaration type: {referenced_declaration}"
            elif isinstance(node, FunctionCall):
                node = node.expression
                while isinstance(
                    node, MemberAccess
                ) and node.referenced_declaration in {
                    GlobalSymbol.FUNCTION_VALUE,
                    GlobalSymbol.FUNCTION_GAS,
                }:
                    node = node.expression
            elif isinstance(node, FunctionCallOptions):
                node = node.expression
            elif isinstance(node, NewExpression):
                type_name = node.type_name
                if isinstance(type_name, (ArrayTypeName, ElementaryTypeName)):
                    return type_name
                elif isinstance(type_name, UserDefinedTypeName):
                    assert isinstance(
                        type_name.referenced_declaration, ContractDefinition
                    )
                    return type_name.referenced_declaration
                else:
                    assert (
                        False
                    ), f"Unexpected function call child node: {node}\n{self.source}"
            elif isinstance(node, TupleExpression):
                if len(node.components) != 1:
                    assert (
                        False
                    ), f"Unexpected function call child node: {node}\n{self.source}"
                node = node.components[0]
            else:
                assert (
                    False
                ), f"Unexpected function call child node: {node}\n{self.source}"

    @property
    @weak_self_lru_cache(maxsize=2048)
    def is_ref_to_state_variable(self) -> bool:
        if self.kind == FunctionCallKind.TYPE_CONVERSION:
            return self.expression.is_ref_to_state_variable
        return False
