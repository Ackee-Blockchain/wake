import logging
from functools import lru_cache, reduce
from operator import or_
from typing import Iterator, List, Optional, Set, Tuple, Union

from woke.ast.enums import (
    FunctionCallKind,
    GlobalSymbolsEnum,
    ModifiesStateFlag,
    StateMutability,
)
from woke.ast.ir.abc import IrAbc, SolidityAbc
from woke.ast.ir.declaration.error_definition import ErrorDefinition
from woke.ast.ir.declaration.event_definition import EventDefinition
from woke.ast.ir.declaration.function_definition import FunctionDefinition
from woke.ast.ir.declaration.modifier_definition import ModifierDefinition
from woke.ast.ir.declaration.struct_definition import StructDefinition
from woke.ast.ir.declaration.variable_declaration import VariableDeclaration
from woke.ast.ir.expression.abc import ExpressionAbc
from woke.ast.ir.expression.function_call_options import FunctionCallOptions
from woke.ast.ir.expression.identifier import Identifier
from woke.ast.ir.expression.member_access import MemberAccess
from woke.ast.ir.expression.new_expression import NewExpression
from woke.ast.ir.expression.tuple_expression import TupleExpression
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcFunctionCall

logger = logging.getLogger(__name__)


class FunctionCall(ExpressionAbc):
    """
    TBD
    """

    _ast_node: SolcFunctionCall
    _parent: SolidityAbc  # TODO: make this more specific

    _arguments: List[ExpressionAbc]
    _expression: ExpressionAbc
    _kind: FunctionCallKind
    _names: List[str]
    _try_call: bool

    _recursion_lock: bool

    def __init__(
        self, init: IrInitTuple, function_call: SolcFunctionCall, parent: SolidityAbc
    ):
        super().__init__(init, function_call, parent)
        self._recursion_lock = False
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
        return self._parent

    @property
    def kind(self) -> FunctionCallKind:
        return self._kind

    @property
    def names(self) -> Tuple[str]:
        return tuple(self._names)

    @property
    def try_call(self) -> bool:
        return self._try_call

    @property
    def expression(self) -> ExpressionAbc:
        return self._expression

    @property
    def arguments(self) -> Tuple[ExpressionAbc]:
        return tuple(self._arguments)

    @property
    @lru_cache(maxsize=2048)
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
    @lru_cache(maxsize=2048)
    def is_ref_to_state_variable(self) -> bool:
        if self.kind == FunctionCallKind.TYPE_CONVERSION:
            return self.expression.is_ref_to_state_variable
        return False

    @property
    @lru_cache(maxsize=2048)
    def modifies_state(self) -> Set[Tuple[IrAbc, ModifiesStateFlag]]:
        if self._recursion_lock:
            return set()
        self._recursion_lock = True
        ret = self.expression.modifies_state | reduce(
            or_, (arg.modifies_state for arg in self.arguments), set()
        )

        if self.kind == FunctionCallKind.FUNCTION_CALL:
            called_function = self.function_called
            if called_function in {
                GlobalSymbolsEnum.SELFDESTRUCT,
                GlobalSymbolsEnum.SUICIDE,
            }:
                ret |= {(self, ModifiesStateFlag.SELFDESTRUCTS)}
            elif called_function in {
                GlobalSymbolsEnum.ADDRESS_TRANSFER,
                GlobalSymbolsEnum.ADDRESS_SEND,
            }:
                ret |= {(self, ModifiesStateFlag.SENDS_ETHER)}
            elif called_function == GlobalSymbolsEnum.ADDRESS_CALL:
                ret |= {(self, ModifiesStateFlag.PERFORMS_CALL)}
            elif called_function == GlobalSymbolsEnum.ADDRESS_DELEGATECALL:
                ret |= {(self, ModifiesStateFlag.PERFORMS_DELEGATECALL)}
            elif (
                called_function
                in {GlobalSymbolsEnum.ARRAY_PUSH, GlobalSymbolsEnum.ARRAY_POP}
                and self.expression.is_ref_to_state_variable
            ):
                ret |= {(self, ModifiesStateFlag.MODIFIES_STATE_VAR)}
            elif called_function == GlobalSymbolsEnum.FUNCTION_VALUE:
                ret |= {(self, ModifiesStateFlag.SENDS_ETHER)}
            elif isinstance(called_function, FunctionDefinition):
                if called_function.state_mutability in {
                    StateMutability.PURE,
                    StateMutability.VIEW,
                }:
                    pass
                elif called_function.body is not None:
                    ret |= called_function.body.modifies_state
                    for modifier in called_function.modifiers:
                        modifier_def = modifier.modifier_name.referenced_declaration
                        assert isinstance(modifier_def, ModifierDefinition)
                        if modifier_def.body is not None:
                            ret |= modifier_def.body.modifies_state
                elif called_function.state_mutability == StateMutability.NONPAYABLE:
                    ret |= {
                        (
                            self,
                            ModifiesStateFlag.CALLS_UNIMPLEMENTED_NONPAYABLE_FUNCTION,
                        )
                    }
                elif called_function.state_mutability == StateMutability.PAYABLE:
                    ret |= {
                        (self, ModifiesStateFlag.CALLS_UNIMPLEMENTED_PAYABLE_FUNCTION)
                    }
                else:
                    assert False
        self._recursion_lock = False
        return ret
