import logging
from functools import lru_cache
from typing import Iterator, List, Optional, Tuple, Union

from woke.ast.enums import FunctionCallKind, GlobalSymbolsEnum
from woke.ast.ir.abc import IrAbc, SolidityAbc
from woke.ast.ir.declaration.error_definition import ErrorDefinition
from woke.ast.ir.declaration.event_definition import EventDefinition
from woke.ast.ir.declaration.function_definition import FunctionDefinition
from woke.ast.ir.declaration.struct_definition import StructDefinition
from woke.ast.ir.declaration.variable_declaration import VariableDeclaration
from woke.ast.ir.expression.abc import ExpressionAbc
from woke.ast.ir.expression.function_call_options import FunctionCallOptions
from woke.ast.ir.expression.identifier import Identifier
from woke.ast.ir.expression.member_access import MemberAccess
from woke.ast.ir.expression.new_expression import NewExpression
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcFunctionCall

logger = logging.getLogger(__name__)


class FunctionCall(ExpressionAbc):
    _ast_node: SolcFunctionCall
    _parent: SolidityAbc  # TODO: make this more specific

    __arguments: List[ExpressionAbc]
    __expression: ExpressionAbc
    __kind: FunctionCallKind
    __names: List[str]
    __try_call: bool

    def __init__(
        self, init: IrInitTuple, function_call: SolcFunctionCall, parent: SolidityAbc
    ):
        super().__init__(init, function_call, parent)
        self.__kind = function_call.kind
        self.__names = list(function_call.names)
        self.__try_call = function_call.try_call

        self.__expression = ExpressionAbc.from_ast(init, function_call.expression, self)
        self.__arguments = [
            ExpressionAbc.from_ast(init, argument, self)
            for argument in function_call.arguments
        ]

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        for argument in self.__arguments:
            yield from argument
        yield from self.__expression

    @property
    def parent(self) -> SolidityAbc:
        return self._parent

    @property
    def kind(self) -> FunctionCallKind:
        return self.__kind

    @property
    def names(self) -> Tuple[str]:
        return tuple(self.__names)

    @property
    def try_call(self) -> bool:
        return self.__try_call

    @property
    def expression(self) -> ExpressionAbc:
        return self.__expression

    @property
    def arguments(self) -> Tuple[ExpressionAbc]:
        return tuple(self.__arguments)

    @property
    @lru_cache(maxsize=None)
    def function_called(
        self,
    ) -> Optional[
        Union[
            EventDefinition,
            ErrorDefinition,
            FunctionDefinition,
            GlobalSymbolsEnum,
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
                        GlobalSymbolsEnum,
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
                        GlobalSymbolsEnum,
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
                    GlobalSymbolsEnum.FUNCTION_VALUE,
                    GlobalSymbolsEnum.FUNCTION_GAS,
                }:
                    node = node.expression
            elif isinstance(node, FunctionCallOptions):
                node = node.expression
            elif isinstance(node, NewExpression):
                return None
            else:
                assert False, f"Unexpected function call child node: {node}"
